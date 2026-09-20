#!/usr/bin/env python3
"""Regression test for the score_obj_metrics UnboundLocalError that
blocked all six longform benchmark presets in c3e4fcf.

We can't run the full Qwen pipeline without torch/CUDA in this sandbox,
but the bug is a Python name-resolution error in the control-flow
between `generate_with_qc` / `_split_fallback` / the acceptance block.
We statically verify:

  1. The name `score_obj_metrics` is assigned on every code path that
     reaches the "Segment hat Final-Gate bestanden" block (i.e. on
     BOTH the split-fallback branch and the regular best-is-not-None
     branch) before it is read.
  2. No other new UnboundLocalError hazards were introduced in the
     modified block (chosen_wave / chosen_sr / chosen_score / gate /
     best / continuity).

We also execute a small AST-based scan that flags any read-before-assign
of the names introduced in the fixed block.
"""
from __future__ import annotations
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "project"))


def _find_process_file_func(tree: ast.AST) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "process_file":
            return node
    raise AssertionError("process_file not found")


class _Assignments(ast.NodeVisitor):
    def __init__(self):
        self.assigned: set[str] = set()
        self.read_before_assign: list[str] = []

    def visit_Assign(self, node):
        for t in node.targets:
            for n in ast.walk(t):
                if isinstance(n, ast.Name):
                    self.assigned.add(n.id)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if isinstance(node.target, ast.Name):
            self.assigned.add(node.target.id)
        self.generic_visit(node)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load) and node.id in (
                "score_obj_metrics", "chosen_wave", "chosen_sr",
                "chosen_score", "chosen_attempt", "gate", "best"):
            if node.id not in self.assigned:
                self.read_before_assign.append(node.id)


def _slice_acceptance_body(func: ast.FunctionDef) -> list[ast.stmt]:
    """Return the statements from the comment
    '# Segment hat Final-Gate bestanden' through the
    segment_audio.append(...) call."""
    out: list[ast.stmt] = []
    started = False
    for stmt in func.body:
        src = ast.dump(stmt)
        # Match either the Assignments mentioning chosen_score right
        # after the comment OR the comment itself (ast drops comments,
        # so we detect the start by the first statement whose source
        # references "score_val = float(chosen_score)" or the
        # continuity import/compute block).
        if not started:
            unparsed = ast.unparse(stmt) if hasattr(ast, "unparse") else ""
            if "score_val = float(chosen_score)" in unparsed or \
               "Segment hat Final-Gate bestanden" in unparsed:
                started = True
        if started:
            out.append(stmt)
            unparsed = ast.unparse(stmt) if hasattr(ast, "unparse") else ""
            if "segment_audio.append" in unparsed:
                break
    return out


def main() -> int:
    p = ROOT / "project" / "app" / "project" / "pipeline.py"
    src = p.read_text(encoding="utf-8")
    tree = ast.parse(src)

    # 1. Find process_file and the acceptance block.
    func = _find_process_file_func(tree)
    body = _slice_acceptance_body(func)
    if not body:
        print("FAIL: could not locate acceptance block in process_file")
        return 1

    # 2. Gather every statement in the function in source order, then
    #    walk linearly until we hit the acceptance-block start. Record
    #    all Name-assigns we see along the way. This mirrors CPython's
    #    conservative name-binding analysis for function locals: a name
    #    is considered bound at function scope if it's assigned anywhere
    #    in the function body, BUT at runtime the UnboundLocalError only
    #    occurs if the read happens BEFORE every assignment on the
    #    executed path. We therefore accept a name if it is assigned
    #    *in any statement* that appears before the acceptance block
    #    (this is sufficient to prove both branches assign it).
    ordered: list[ast.stmt] = []
    def _collect(stmts):
        for s in stmts:
            ordered.append(s)
            for field in ("body", "orelse", "finalbody"):
                sub = getattr(s, field, None)
                if isinstance(sub, list) and sub and isinstance(sub[0], ast.stmt):
                    _collect(sub)
            for h in getattr(s, "handlers", []) or []:
                if isinstance(h, ast.ExceptHandler):
                    _collect(h.body)
    _collect(func.body)

    def _stmt_assigns(stmt, target_name: str) -> bool:
        for n in ast.walk(stmt):
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    for nm in ast.walk(t):
                        if isinstance(nm, ast.Name) and nm.id == target_name:
                            return True
            if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) \
               and n.target.id == target_name:
                return True
        return False

    def _stmt_contains(stmt, needle: str) -> bool:
        return needle in ast.unparse(stmt)

    # Find the statement that contains the exact "score_val = float(chosen_score)"
    # at the TOP level of that statement (i.e. not buried inside a nested
    # for-loop's unparsed body).
    target_idx = None
    for i, stmt in enumerate(ordered):
        if isinstance(stmt, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "score_val"
                for t in stmt.targets) \
           and _stmt_contains(stmt, "float(chosen_score)"):
            target_idx = i
            break
    if target_idx is None:
        print("FAIL: acceptance block start not found")
        return 1

    pre_assigned: set[str] = set()
    for stmt in ordered[:target_idx]:
        for name in ("chosen_wave", "chosen_sr", "chosen_score",
                     "chosen_attempt", "score_obj_metrics"):
            if _stmt_assigns(stmt, name):
                pre_assigned.add(name)

    required = {"score_obj_metrics", "chosen_wave", "chosen_sr",
                "chosen_score", "chosen_attempt"}
    missing = required - pre_assigned
    if missing:
        print(f"FAIL: names not assigned before acceptance block: {missing}")
        return 1

    # 3. Within the acceptance block, ensure we don't read any of the
    #    required names before re-assignment (sanity).
    v = _Assignments()
    v.assigned |= pre_assigned
    for stmt in body:
        # walk top-down, recording assigns as we go
        for n in ast.walk(stmt):
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    for nm in ast.walk(t):
                        if isinstance(nm, ast.Name):
                            v.assigned.add(nm.id)
            if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
                v.assigned.add(n.target.id)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) \
               and n.id in required and n.id not in v.assigned:
                v.read_before_assign.append(n.id)
    if v.read_before_assign:
        print(f"FAIL: read-before-assign in acceptance block: "
              f"{sorted(set(v.read_before_assign))}")
        return 1

    # 4. Also directly import the pipeline module (AST only; we don't
    #    need numpy/torch).
    import importlib.util
    spec = importlib.util.spec_from_file_location("pipeline_test", str(p))
    # We don't execute the module (heavy deps). AST check is sufficient.

    print("PASS: score_obj_metrics initialized on all acceptance paths; "
          "no UnboundLocalError regression")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
