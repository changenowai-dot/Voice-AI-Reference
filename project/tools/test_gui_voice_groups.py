#!/usr/bin/env python3
"""Headless test for GUI voice grouping (no tkinter)."""
from __future__ import annotations
import sys, types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "project"
sys.path.insert(0, str(PROJECT))

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

from app.voices.registry import VoiceRegistry, tier_for  # noqa: E402


def _flatten(g):
    return {r["voice_id"]: (grp, r) for grp, rows in g.items() for r in rows}


def main() -> int:
    reg = VoiceRegistry()
    fails = 0

    # Structural invariants pro Sprache
    for lang in ("German", "English"):
        g = vv.voice_groups(lang, reg)
        # VD-E muss in locked stehen
        locked = [r for r in g["locked"] if r["voice_id"] == "vd_e"]
        if not locked:
            print(f"[FAIL] {lang}: VD-E fehlt in locked"); fails += 1
        else:
            vd = locked[0]
            if lang == "German":
                if not vd.get("selectable"):
                    print(f"[FAIL] {lang}: VD-E muss auswählbar sein"); fails += 1
                else:
                    print(f"[PASS] {lang} VD-E locked + selectable")
            else:
                if vd.get("selectable"):
                    print(f"[FAIL] {lang}: VD-E darf in Englisch NICHT auswählbar sein")
                    fails += 1
                else:
                    print(f"[PASS] {lang} VD-E locked + disabled (nur Deutsch)")

        # Custom-Voices müssen selectable sein
        for r in g["custom"]:
            if not r.get("selectable"):
                print(f"[FAIL] {lang} custom {r['voice_id']} not selectable")
                fails += 1
        print(f"[PASS] {lang} {len(g['custom'])} Custom-Voices alle auswählbar")

        # Candidates: niemals selectable, REJECTED immer in candidates
        for r in g["candidates"]:
            if r.get("selectable"):
                print(f"[FAIL] {lang} candidate {r['voice_id']} selectable=True")
                fails += 1
        print(f"[PASS] {lang} {len(g['candidates'])} Candidates, keine auswählbar")

        # Clone: wenn Eintrag dort steht, muss er selectable UND available sein
        for r in g["clone"]:
            if not r.get("selectable") or not r.get("available"):
                print(f"[FAIL] {lang} clone {r['voice_id']} not selectable/available")
                fails += 1
        print(f"[PASS] {lang} {len(g['clone'])} Clone-Voices, alle auswählbar")

        # REJECTED-Tier muss immer in candidates landen (niemals clone)
        for r in g["clone"] + g["custom"]:
            profile = reg._profiles.get(r["voice_id"], {})
            if tier_for(profile) == "REJECTED" and r["voice_id"] != "vd_e":
                print(f"[FAIL] {lang} REJECTED {r['voice_id']} darf nicht in clone/custom stehen")
                fails += 1
        print(f"[PASS] {lang} keine REJECTED-Voices in clone/custom")

        # Status-Labels der verfügbaren Stimmen müssen [VERFÜGBAR] enthalten
        for r in g["clone"] + g["custom"]:
            if "[VERFÜGBAR]" not in r["status"] and r["voice_id"] != "vd_e":
                print(f"[FAIL] {lang} {r['voice_id']} status label fehlt [VERFÜGBAR]: {r['status']}")
                fails += 1
        print(f"[PASS] {lang} verfügbare Stimmen haben [VERFÜGBAR] Label")

    # Ein paar konkrete Stimmen müssen auftauchen (in welcher Gruppe
    # auch immer – je nachdem, ob Bundles im aktuellen Checkout liegen)
    must_exist = ["vd_e", "ryan", "aiden", "de_male_deep_natural_conversational_01",
                  "en_male_warm_storytelling_authoritative_02"]
    for lang in ("German", "English"):
        g = vv.voice_groups(lang, reg)
        flat = _flatten(g)
        for vid in must_exist:
            if vid not in flat:
                print(f"[FAIL] {lang} Stimme {vid} fehlt im Listing"); fails += 1
    print(f"[PASS] alle erwarteten voice_ids sind in DE/EN gelistet")

    if fails:
        print(f"\n{fails} GUI VOICE-GROUP TEST(S) FAILED")
        return 1
    print("\nALL GUI VOICE-GROUP TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
