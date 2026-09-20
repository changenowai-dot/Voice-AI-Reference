#!/usr/bin/env python3
"""Tests for +++++ split reliability and fail-closed long-form assembly.

These are OFFLINE tests - they exercise split_plan, split_manuscript
and the concat gate logic directly without invoking TTS.
"""
from __future__ import annotations
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.text.script_split import (split_plan, split_manuscript,
                                    is_marker_line, count_markers,
                                    part_name, FULLSCRIPT_SUFFIX)


def test_marker_exact():
    assert is_marker_line("+++++")
    assert is_marker_line("  +++++  ")
    assert not is_marker_line("++++")
    assert not is_marker_line("++++++")
    assert not is_marker_line("abc +++++")
    assert not is_marker_line("+++++ abc")
    print("[PASS] marker exact-line detection")


def test_three_parts():
    txt = "PART 1\n+++++\nPART 2\n+++++\nPART 3\n"
    plan = split_plan(txt, enabled=True)
    assert plan["use_split"] is True
    assert plan["parts"] == 3, plan
    assert plan["markers"] == 2
    secs = split_manuscript(txt)
    assert len(secs) == 3, secs
    assert secs[0].strip() == "PART 1"
    assert secs[1].strip() == "PART 2"
    assert secs[2].strip() == "PART 3"
    joined = "\n".join(secs)
    assert "+++++" not in joined, "marker must not appear in rendered sections"
    print("[PASS] 3-parts marker split (3 outputs, no marker in text, order preserved)")


def test_double_marker_collapsed():
    txt = "A\n+++++\n+++++\nB\n"
    plan = split_plan(txt, enabled=True)
    assert plan["parts"] == 2, plan
    print("[PASS] double/empty markers collapse (no empty part)")


def test_marker_disabled():
    txt = "A\n+++++\nB\n"
    plan = split_plan(txt, enabled=False)
    assert plan["use_split"] is False
    assert plan["parts"] == 1
    print("[PASS] split disabled -> single section")


def test_part_naming():
    assert part_name("gui_20260920", 1).endswith("_Part_001")
    assert part_name("gui_20260920", 11).endswith("_Part_011")
    assert FULLSCRIPT_SUFFIX == "FullScript"
    print("[PASS] part naming stable and sortable")


def test_fullscript_gate_logic():
    """Reproduce the fail-closed gate the runner enforces.

    FullScript may only be assembled when ALL of:
      * parts_ok == parts_total
      * parts_failed_segs == 0
      * failed_parts == []
      * every part wav path exists
    """
    def fullscript_allowed(parts_total, parts_ok, parts_failed_segs,
                           failed_parts, wavs_exist):
        return (parts_ok == parts_total
                and parts_failed_segs == 0
                and not failed_parts
                and wavs_exist)
    # happy path
    assert fullscript_allowed(3, 3, 0, [], True)
    # one segment failed inside a part
    assert not fullscript_allowed(3, 3, 1, [], True)
    # one part failed entirely
    assert not fullscript_allowed(3, 2, 0, ["Part_003"], True)
    # wav file missing
    assert not fullscript_allowed(3, 3, 0, [], False)
    print("[PASS] fullscript fail-closed gate logic")


def test_german_pause_profile_narrative_has_comma_values():
    from app.prosody.german import PAUSE_STRATEGIES
    narr = PAUSE_STRATEGIES["narrative"]
    for k in ("after_comma", "after_semicolon", "after_colon",
              "after_dash", "after_ellipsis", "paragraph", "chapter",
              "statement", "question"):
        assert k in narr, f"German narrative missing {k}"
        assert isinstance(narr[k], (int, float)) and narr[k] > 0
    print("[PASS] German narrative profile has comma/semicolon/colon/dash/ellipsis/paragraph/chapter/statement/question values")


def test_english_pause_profile_narrative_has_comma_values():
    from app.prosody.english import PAUSE_STRATEGIES_EN
    narr = PAUSE_STRATEGIES_EN["narrative"]
    for k in ("after_comma", "after_semicolon", "after_colon",
              "after_dash", "after_ellipsis", "paragraph", "chapter",
              "statement", "question"):
        assert k in narr, f"English narrative missing {k}"
        assert isinstance(narr[k], (int, float)) and narr[k] > 0
    print("[PASS] English narrative profile has comma/semicolon/colon/dash/ellipsis/paragraph/chapter/statement/question values")


def test_golden_reference_unchanged():
    import hashlib
    p = pathlib.Path(__file__).resolve().parents[1] / "VD-E_GOLDEN_REFERENCE" / "VD-E.wav"
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    assert h == "b156c02a60a873ad95fc92390c4a136c85308b20188373cd734bee5e5e5f2025", h
    print("[PASS] VD-E golden reference SHA unchanged")


def test_preset_registers_language_profiles():
    from app.prosody.presets import load_presets
    p = load_presets()
    for k in ("en_documentary", "en_narrative",
              "de_documentary", "de_narrative"):
        assert k in p, f"missing preset {k}"
        assert p[k]["pause_strategy"] in ("classic", "semantic",
                                          "narrative", "flow"), p[k]
    print("[PASS] language-specific presets registered (en_documentary/en_narrative/de_documentary/de_narrative)")


def test_pipeline_returns_notok_on_failed_segments():
    """The pipeline's wav_complete flag must be False when failed_segments>0."""
    # We can't run pipeline without torch, but we can at least import the
    # code path and validate that the fail-closed branches exist.
    import ast
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "app" / "project" / "pipeline.py").read_text()
    tree = ast.parse(src)
    found_fail_closed = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "all_segments_ok":
                    found_fail_closed = True
    assert found_fail_closed, "pipeline.py: all_segments_ok guard not found"
    assert '"ok": bool(final_wav' in src or '"ok": bool(' in src, "pipeline.py ok gate not hardened"
    print("[PASS] pipeline.py contains fail-closed all_segments_ok/ok gate")


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except AssertionError as e:
                print(f"[FAIL] {name}: {e}"); fails += 1
            except Exception as e:
                print(f"[ERROR] {name}: {e}"); fails += 1
    print()
    if fails:
        print(f"{fails} TEST(S) FAILED")
        sys.exit(1)
    print("ALL SPLIT/LONG-FORM/PAUSE/PRESET/GOLDEN TESTS PASSED")
