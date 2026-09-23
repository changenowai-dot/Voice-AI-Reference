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
    # --- Teilchenfamilie (Host-Befund 2026-09: Pro-TO-nen/Noi-tro-NEN
    # falsch -> Identity; Host bestaetigt Identity-Muster als gut) ---
    ("Protonen und Neutronen befinden sich im Atomkern.",
     "Protonen und Neutronen befinden sich im Atomkern.",
     "Pro-TO-nen Noi-tro-NEN"),
    ("Ein Proton ist positiv geladen, ein Neutron neutral, ein Elektron negativ.",
     "Ein Proton ist positiv geladen, ein Neutron neutral, ein Elektron negativ.",
     "PRO-ton NOI-tron E-lek-TRON"),
    # --- Regressions-Anker (Phase 7, muessen unverändert bleiben) ---
    ("Der Algorithmus und die Algorithmen sind die Basis der Informatik.",
     "Algorithmus und die Algorithmen", None),
    ("Quantenphysik und Quantenmechanik beschreiben das Quantenverhalten.",
     "Quantenphysik und Quantenmechanik", None),
    ("Statistik und Wahrscheinlichkeit erklären Zufall.",
     "Statistik und Wahrscheinlichkeit", None),
    ("Die Theorie der Mathematik ist mathematisch fundiert.",
     "Theorie der Mathematik ist mathematisch", None),
    ("Bewusstsein ist ein Prozess des Gehirns.",
     "Bewusstsein ist ein Prozess", "be-WUSST-sein"),
    ("Die Neurowissenschaft und die Psychologie arbeiten zusammen.",
     "Neurowissenschaft und die Psychologie", None),
    # --- Batch 2 (User-Hoerbefunde 2026-09 #2, Identity) ---
    ("Die Daten werden vom Prozessor verarbeitet.",
     "Die Daten werden vom Prozessor verarbeitet", "DA-ten"),
    ("Eine Matrix ordnet Zahlen, ein Vektor hat Richtung.",
     "Eine Matrix ordnet Zahlen, ein Vektor hat Richtung",
     "MA-trix VEK-tor"),
    ("Jede Gleichung nutzt den Logarithmus.",
     "Jede Gleichung nutzt den Logarithmus",
     "GLEI-chung Lo-ga-RITH-mus"),
    ("Der Quellcode liegt in der Datenbank.",
     "Der Quellcode liegt in der Datenbank",
     "KWELL-kod DA-ten-bank"),
    ("Metaphysik und Ontologie sind Philosophie.",
     "Metaphysik und Ontologie sind", "Me-ta-FY-sik On-to-LO-gie"),
    ("Die Erkenntnistheorie untersucht Wissen.",
     "Die Erkenntnistheorie untersucht Wissen",
     "teo-RIE"),
    # Philosoph: bewusst UNVERAENDERT (unsicherer Hörbefund, Host-A/B
    # steht aus) - Respell FI-lo-sof bleibt Erwartung.
    ("Der Philosoph fragt nach Erkenntnis.",
     "FI-lo-sof", None),
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
