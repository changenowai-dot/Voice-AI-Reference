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
# Psychologie/Neurowissenschaft sind seit dem bestätigten R2/R3-Stand
# Identity-Mappings (plain in Produktion); die alten Respell-Erwartungen
# beschrieben den Vor-R2-Stand und schlugen zu Unrecht an.
# Atom-/Atome-/Atomkern-/Zelle-/Zellen-Checks sichern die Identity-Regeln
# (kein Bindestrich-/GROSS-Respell mehr, natürliche Orthographie bleibt).
CHECKS = [
    ("Der Philosoph steht da.",        "FI-lo-sof",      "Phi-LO-sof"),
    ("Die Philosophie ist alt.",       "fi-lo-zo-FIE",   "Fi-lo-so-FIE"),
    ("Ein philosophischer Geist.",     "fi-lo-ZO-fi-scher", None),
    ("Die Psychologie des Menschen.",  "Psychologie",    "Psy-cho-LO-gie"),
    ("Die Neurowissenschaft wächst.",  "Neurowissenschaft", "Neu-ro-WIS-sen-schaft"),
    ("Die Quantentheorie gilt.",       "Quan-ten-teo-RIE", None),
    ("Ein Physiker rechnet.",          "FY-si-ker",      None),
    ("Das Atom, die Atome, der Atomkern.",
     "Das Atom, die Atome, der Atomkern.", "A-TOM"),
    ("Die Zelle und die Zellen.",
     "Die Zelle und die Zellen.", "TSEL-"),
    # "Energie" hat ein eigenes, von dieser Familie unabhängiges Respell
    # (außerhalb des Umfangs) – geprüft wird nur: Flexionen + "Atomen"
    # bleiben natürlich, kein A-TO-Respell mehr.
    ("Ein atomarer Reaktor, atomare Energie, bei Atomen.",
     "atomarer Reaktor, atomare", "A-TO-"),
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
