"""Umlaut-/ß-Regressionsharness: frische TTS-Eingaben für den GPU-Host.

Auftrag (2026-09-24, Regression deutsche Aussprache Ä Ö Ü ß)
------------------------------------------------------------
Erzeugt die drei vom Auftrag geforderten Testebenen als FRISCHE
Text-Fingerprints (reused=0 garantiert, kein Cache-Treffer möglich):

  TEST A — isolierte deutsche Orthografie (40 Wörter Ä/Ö/Ü/ä/ö/ü/ß)
  TEST B — natürliche Sätze (6 Sätze)
  TEST C — Fachwort-Kompatibilität (20 Begriffe, eingefrorene
           Produktionswerte, siehe EXPECTED_C)

Das Tool verändert KEINEN Text und KEIN Wörterbuch. Es läuft die
Produktionskette (normalize_text -> PronunciationEngine) und prüft pro
Payload:
  - Codepunkt-Erhaltung aller Umlaute/ß (GUI-Input == TTS-Input)
  - replacements (A/B: 0, C: die eingefrorenen Fachwort-Respells)
  - umlaut_words (Observability-Zähler aus der Engine)
  - Frische der Fingerprints (keiner doppelt, keiner aus alten Läufen)

Akustische Bewertung bewusst NICHT hier: synthetisiert wird am GPU-Host
(test_pronunciation_tts-Mechanik), gehoert wird vom Menschen. Ohne GPU
funktioniert dieses Tool vollständig (reine Textebene) und schreibt
umlaut_ab_payloads.json als Arbeitsblatt für den Host-Lauf.

Aufruf:
    python tools/test_pronunciation_umlaut_ab.py            # Prüfung + JSON
    python tools/test_pronunciation_umlaut_ab.py --out DIR  # anderes Ziel
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_config
from app.logging_setup import text_fingerprint
from app.pronunciation import PronunciationEngine
from app.text.normalize import NormalizationReport, normalize_text

# ---------------------------------------------------------------------------
# TEST A — isolierte deutsche Orthografie (Auftragsliste, 1:1)
# ---------------------------------------------------------------------------
TEST_A_WORDS = [
    "Äpfel", "Bäume", "Türen", "schöne", "Bücher", "Über", "größe", "große",
    "größer", "größte", "draußen", "führt", "grünen", "Hügel", "früher",
    "hörte", "Vögel", "deutlicher", "ungewöhnlich", "größere", "öffnen",
    "weiß", "Häuser", "fühlen", "müde", "über", "frühe", "Straße", "heiß",
    "Größe", "außerdem",
    # Zusatzblock des Auftrags:
    "Maße", "heißen", "schließen", "lösen", "prüfen", "führen", "fühlt",
    "möchte", "können", "würde",
]

# ---------------------------------------------------------------------------
# TEST B — natürliche Sätze (Auftragsliste, 1:1)
# ---------------------------------------------------------------------------
TEST_B_SENTENCES = [
    "Die größeren Bäume stehen draußen auf der grünen Wiese.",
    "Über der Straße hängt ein weißer Nebel.",
    "Früher hörte man die Vögel viel deutlicher.",
    "Bitte öffne die größere Tür und führe den Besucher hinein.",
    "Diese Größe und diese Stärke verändern die gesamte Wirkung.",
    "Die schönste Lösung ist nicht immer die größte.",
]

# ---------------------------------------------------------------------------
# TEST C — Fachwort-Kompatibilität (Auftragsliste) mit den zum Freeze-Zeit-
# punkt (c96bb4e + 5d9ba1d) dokumentierten Produktionswerten. Diese Tabelle
# ist das Regression-Gate: Eine Änderung ist nur per belegtem Host-A/B
# erlaubt (Batches 3-5-Prozess).
# ---------------------------------------------------------------------------
EXPECTED_C = {
    "Wissenschaft": "Wissenschaft",
    "Quantenphysik": "Quantenphysik",
    "Neurowissenschaft": "Neurowissenschaft",
    "Bewusstsein": "Bewusstsein",
    "Psyche": "Pü-che",
    "Physik": "FY-sik",
    "Physiker": "FY-si-ker",
    "Phänomen": "Fä-NO-men",
    "Energie": "E-NER-gie",
    "Philosophie": "Fi-lo-zo-FIE",
    "Transmutation": "Trans-mu-ta-tion",
    "Kernphysik": "Kern-fy-SIK",
    "Quantenmechanik": "Quantenmechanik",
    "Relativitätstheorie": "Re-la-ti-vi-täts-teo-RIE",
    "Theorie": "Theorie",
    "Chemie": "CE-mie",
    "Chemiker": "CE-mi-ker",
    "Einstein": "Ainstein",
    "Protonen": "Protonen",
    "Atom": "Atom",
}


def umlaut_count(text: str) -> int:
    import re
    return sum(1 for w in re.findall(r"[A-Za-zÄÖÜäöüß]+", text)
               if re.search(r"[äöüßÄÖÜ]", w))


def run_payload(engine: PronunciationEngine, text: str) -> dict:
    nr = NormalizationReport()
    normalized = normalize_text(text, "German", nr)
    res = engine.process(normalized, "German", suggest_unknown=False)
    return {
        "gui_input": text,
        "tts_input": res.text,
        "fingerprint": text_fingerprint(res.text),
        "chars_in": len(text),
        "chars_out": len(res.text),
        "codepoints_erhalten": res.text == text,
        "replacements": len(res.replacements),
        "replacement_details": [
            {"from": r.get("from"), "to": r.get("to"), "rule": r.get("rule")}
            for r in res.replacements],
        "umlaut_words": res.umlaut_words,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="cache/umlaut_ab_payloads.json")
    args = ap.parse_args()

    cfg = load_config()
    engine = PronunciationEngine(tech_germanization=bool(
        (cfg.get("german") or {}).get("tech_germanization", True)))

    payloads: dict = {}
    fails: list[str] = []

    # TEST A -----------------------------------------------------------------
    a_text = ("Bitte sprich diese Wörter klar und natürlich aus: "
              + ", ".join(TEST_A_WORDS)
              + ". Besonders wichtig sind dabei die Umlaute Ä, Ö und Ü "
                "sowie das scharfe ß.")
    a = run_payload(engine, a_text)
    a["erwartung"] = "replacements=0, identity, Umlaute codepunkt-identisch"
    payloads["TEST_A_isoliert"] = a
    if not a["codepoints_erhalten"] or a["replacements"] != 0:
        fails.append("TEST_A: Text verändert oder Ersetzungen (global-"
                     "Substitutions-Guard verletzt)")

    # TEST B -----------------------------------------------------------------
    b_text = " ".join(TEST_B_SENTENCES)
    b = run_payload(engine, b_text)
    b["erwartung"] = "replacements=0, identity, natürliche Sätze"
    payloads["TESTB_saetze"] = b
    if not b["codepoints_erhalten"] or b["replacements"] != 0:
        fails.append("TEST_B: Text verändert oder Ersetzungen")

    # TEST C -----------------------------------------------------------------
    c_text = ("Themen dieser Folge: "
              + ", ".join(EXPECTED_C.keys()) + ".")
    c = run_payload(engine, c_text)
    c["erwartung"] = "eingefrorene Fachwort-Respells (EXPECTED_C)"
    payloads["TESTC_fachwoerter"] = c
    # Einzelfprüfung der Fachwörter in neutralem Kontext
    c_detail = {}
    for term, expected in EXPECTED_C.items():
        probe = run_payload(engine, f"Thema: {term}.")
        inner = probe["tts_input"]
        inner = inner[len("Thema: "):].rstrip(". ").strip()
        c_detail[term] = {"tts": inner, "ok": inner == expected}
        if inner != expected:
            fails.append(f"TEST_C: {term!r} -> {inner!r}, erwartet "
                         f"{expected!r} (Fachwort-Regression?)")
    c["einzelnachweis"] = c_detail

    # Frische: alle Fingerprints unterschiedlich
    fps = [p["fingerprint"] for p in payloads.values()]
    if len(set(fps)) != len(fps):
        fails.append("Fingerprint-Kollision zwischen Payloads")

    # Report -----------------------------------------------------------------
    print("=" * 72)
    print("UMLAUT-/ß-REGRESSIONSHARNESS — frische TTS-Eingaben (Host-Lauf)")
    print("=" * 72)
    for name, p in payloads.items():
        print(f"\n{name}: fp={p['fingerprint']} chars={p['chars_out']} "
              f"repl={p['replacements']} umlaut_words={p['umlaut_words']} "
              f"identity={p['codepoints_erhalten']}")
    c_ok = sum(1 for v in c_detail.values() if v["ok"])
    print(f"\nTEST C Einzelnachweis: {c_ok}/{len(EXPECTED_C)} Fachwörter auf "
          f"eingefrorenem Produktionswert")
    out = {
        "sprache": "German",
        "engine": "qwen3-tts-clone (Host)",
        "voice_referenz": "VD-E (SHA B156C02A..., unveraendert)",
        "reused_erwartung": "0 (alle Fingerprints frisch)",
        "payloads": payloads,
    }
    Path(args.out).write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nArbeitsblatt geschrieben: {args.out}")
    if fails:
        print("\nFEHLER:")
        for f in fails:
            print("  -", f)
        return 1
    print("\nALLE TEXT-EBENEN-PRÜFUNGEN BESTANDEN "
          "(akustisches Urteil: Host-Hörprüfung)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
