#!/usr/bin/env python3
"""Smoke / unit check: new tooling uses the canonical HardwareInfo API.

Runs without GPU/torch. Verifies:
  - materialize_references.py and stage2_oneshot.py do NOT access
    non-existent HardwareInfo.device / .dtype attributes.
  - HardwareInfo dataclass exposes the documented fields used by the
    codebase (mode, gpu_name, etc.) and recommend_torch_dtype works.
  - imports succeed without touching torch.
"""
from __future__ import annotations
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] if False else Path(__file__).resolve().parents[1]
# tool lives under ROOT/project/tools — two parents up is the repo root.
# Actually: __file__ = ROOT/project/tools/test_hardware_api.py  => parents[1]=project, parents[2]=ROOT.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "project"))

from app.hardware.detector import HardwareInfo, recommend_torch_dtype  # noqa: E402


FORBIDDEN_ACCESSORS = ["hw.device", "hw.dtype", "hardware.device",
                       "hardware.dtype", "info.device", "info.dtype"]


def _assert_no_forbidden_attr(path: Path) -> list[str]:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))
    errors: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in ("hw", "hardware", "info") \
               and node.attr in ("device", "dtype"):
                errors.append(f"{path}:{node.lineno}: "
                              f"{node.value.id}.{node.attr}")
    return errors


def main() -> int:
    errors: list[str] = []
    targets = [
        ROOT / "project" / "tools" / "materialize_references.py",
        ROOT / "stage2_oneshot.py",
    ]
    for t in targets:
        if not t.exists():
            errors.append(f"missing file: {t}")
            continue
        errors.extend(_assert_no_forbidden_attr(t))

    # HardwareInfo fields sanity
    hw = HardwareInfo()
    for attr in ("mode", "gpu_name", "cuda_available", "device_capability"):
        if not hasattr(hw, attr):
            errors.append(f"HardwareInfo missing expected field: {attr}")
    if recommend_torch_dtype(hw) != "float32":
        errors.append("recommend_torch_dtype(cpu) should return float32")
    hw_gpu = HardwareInfo(mode="gpu")
    if recommend_torch_dtype(hw_gpu) != "bfloat16":
        errors.append("recommend_torch_dtype(gpu) should return bfloat16")

    # Import checks (no torch required at import time)
    for mod in ["app.hardware.detector", "app.voices.registry"]:
        try:
            __import__(mod)
        except Exception as e:                     # noqa: BLE001
            errors.append(f"import {mod} failed: {e}")

    if errors:
        print("FAIL")
        for e in errors:
            print(" ", e)
        return 1
    print("PASS: tooling uses canonical HardwareInfo API (no hw.device/hw.dtype)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
