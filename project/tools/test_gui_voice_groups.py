#!/usr/bin/env python3
"""Headless test for GUI voice grouping (no tkinter)."""
from __future__ import annotations
import sys, types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "project"
sys.path.insert(0, str(PROJECT))

# Load voice_view without importing the app.gui package (__init__.py pulls
# in app.py which imports tkinter). We register a fake parent package
# that exposes just ``voice_view`` so relative imports resolve.
import importlib.util as _ilu

gui_pkg = types.ModuleType("app.gui")
gui_pkg.__path__ = [str(PROJECT / "app/gui")]
app_pkg = types.ModuleType("app")
app_pkg.__path__ = [str(PROJECT / "app")]
sys.modules["app"] = app_pkg
sys.modules["app.gui"] = gui_pkg

VV_PATH = PROJECT / "app/gui/voice_view.py"
spec = _ilu.spec_from_file_location("app.gui.voice_view", VV_PATH)
vv = _ilu.module_from_spec(spec)
sys.modules["app.gui.voice_view"] = vv
spec.loader.exec_module(vv)

from app.voices.registry import VoiceRegistry  # noqa: E402


def _flatten(g):
    return {r["voice_id"]: (grp, r) for grp, rows in g.items() for r in rows}


def main() -> int:
    reg = VoiceRegistry()
    fails = 0
    cases = [
        ("English", [
            ("en_male_ultra_deep_calm_resonant_01", "candidates"),
            ("en_male_deep_01",                         "clone"),
            ("en_male_warm_storytelling_authoritative_02", "clone"),
            ("en_male_velvet_baritone_01",             "clone"),
            ("aiden",                                   "custom"),
            ("ryan",                                    "custom"),
        ]),
        ("German", [
            ("vd_e",                                    "locked"),
            ("de_male_deep_academic_01",                "candidates"),
            ("de_male_cinematic_restrained_01",         "candidates"),
            ("de_male_deep_natural_conversational_01",  "clone"),
            ("de_male_warm_storytelling_authoritative_01","clone"),
        ]),
    ]
    for lang, must in cases:
        g = vv.voice_groups(lang, reg)
        flat = _flatten(g)
        for vid, expected in must:
            if vid not in flat:
                print(f"[FAIL] {lang} listing missing {vid}"); fails += 1; continue
            actual, row = flat[vid]
            if actual != expected:
                print(f"[FAIL] {lang} {vid} group={actual} expected={expected}")
                fails += 1; continue
            print(f"[PASS] {lang} {vid} -> {actual}")
        # Candidates must not be selectable
        for r in g["candidates"]:
            if r.get("selectable", False):
                print(f"[FAIL] {lang} candidate {r['voice_id']} selectable=True")
                fails += 1
        # Clone entries without reference must not be selectable
        for r in g["clone"]:
            if not r.get("available", True) and r.get("selectable", False):
                print(f"[FAIL] {lang} unavailable clone {r['voice_id']} selectable")
                fails += 1
    if fails:
        print(f"\n{fails} GUI VOICE-GROUP TEST(S) FAILED")
        return 1
    print("\nALL GUI VOICE-GROUP TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
