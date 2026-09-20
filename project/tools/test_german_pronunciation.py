#!/usr/bin/env python3
"""German pronunciation regression tests (specialist terms).

These are ENGINE-LEVEL tests — they verify that tech-germanization
emits the expected respelling tokens. They do NOT require the TTS
model (no GPU, no torch) and are safe to run in CI/sandbox.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pronunciation import PronunciationEngine

# (input fragment, must-appear-respelling, must-NOT-appear-respelling)
CHECKS = [
    ("Der Philosoph steht da.",        "FI-lo-sof",      "Phi-LO-sof"),
    ("Die Philosophie ist alt.",       "fi-lo-zo-FIE",   "Fi-lo-so-FIE"),
    ("Ein philosophischer Geist.",     "fi-lo-ZO-fi-scher", None),
    ("Die Psychologie des Menschen.",  "Psy-cho-LO-gie", None),
    ("Die Neurowissenschaft wächst.",  "Neu-ro-WIS-sen-schaft", None),
    ("Die Quantentheorie gilt.",       "Quan-ten-teo-RIE", None),
    ("Ein Physiker rechnet.",          "FY-si-ker",      None),
]


def main() -> int:
    p = PronunciationEngine(tech_germanization=True)
    fails = 0
    for text, must, must_not in CHECKS:
        out = p.process(text, "German", suggest_unknown=False).text
        ok = True
        if must not in out:
            print(f"[FAIL] {text!r}\n        expected substring {must!r}, got:\n        {out!r}")
            ok = False; fails += 1
        if must_not and must_not in out:
            print(f"[FAIL] {text!r}\n        forbidden substring {must_not!r} in:\n        {out!r}")
            ok = False; fails += 1
        if ok:
            print(f"[PASS] {text}")
    if fails:
        print(f"\n{ fails } PRONUNCIATION TEST(S) FAILED")
        return 1
    print("\nALL GERMAN PRONUNCIATION TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
