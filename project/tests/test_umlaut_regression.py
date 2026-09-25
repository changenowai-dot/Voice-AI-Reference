"""Umlaut-/ß-Regression-Gates (Auftrag 2026-09-24).

Deckt die vom Auftrag geforderten Ebenen auf TEXTEBENE ab (akustische
Beurteilung bleibt dem GPU-Host-Hörtest vorbehalten, siehe
tools/test_pronunciation_umlaut_ab.py):

1. Codepunkt-Erhaltung: Ä Ö Ü ä ö ü ß überleben GUI-Input -> TTS-Input
   bitidentisch (keine stille NFC/NFD/transliterierende Umwandlung).
2. Keine globalen Ersatzschreibweisen: ä->ae / ö->oe / ü->ue / ß->ss sind
   verboten; normale deutsche Wörter bleiben identity (replacements=0).
3. Fachwort-Kompatibilität: die eingefrorenen Produktionswerte
   (Psyche/Physik/Phänomen/Energie/Philosophie/Transmutation/Kernphysik
   usw.) dürfen durch die Umlaut-Fixes NICHT ändern.
4. Umlaut-Observability: PREPROCESS_END weist umlaut_words aus.
5. PACING_HINT_DE verwendet echte deutsche Orthografie (kein
   "natuerlich/Saetzen"-ASCII im deutschen Prompt).
6. Namens-Heuristik: Umlautwörter sind "deutsch wirkend"; satzinitiale
   Großschreibung ist kein Eigennamen-Signal (unknown_problem_terms
   entfällt für normale deutsche Wörter).
Wörterbuch/pronunciation.json werden NICHT verändert (reiner Lese-Lauf).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app.config import load_config
from app.pronunciation import PronunciationEngine
from app.pronunciation.names import _looks_german, scan_names
from app.text.normalize import NormalizationReport, normalize_text

USER_TEST_TEXT = (
    "Äpfel, Bäume, Türen und schöne Bücher stehen auf dem Tisch. "
    "Über ihnen hängt eine große Lampe, und draußen führt eine schmale "
    "Straße durch die grünen Hügel. Früher hörte man dort die Vögel viel "
    "deutlicher, doch heute ist die Umgebung ungewöhnlich ruhig. Die "
    "größere Tür lässt sich langsam öffnen, während draußen bereits "
    "weißer Nebel über die Häuser zieht. Bitte sprich diese Wörter klar "
    "und natürlich aus: größer, größte, schön, öffnen, führen, hören, "
    "fühlen, müde, über, frühe, Straße, weiß, heiß, Größe und außerdem. "
    "Besonders wichtig sind dabei die Umlaute Ä, Ö und Ü sowie das "
    "scharfe ß.")

TEST_A_WORDS = [
    "Äpfel", "Bäume", "Türen", "schöne", "Bücher", "Über", "größe",
    "große", "größer", "größte", "draußen", "führt", "grünen", "Hügel",
    "früher", "hörte", "Vögel", "deutlicher", "ungewöhnlich", "größere",
    "öffnen", "weiß", "Häuser", "fühlen", "müde", "über", "frühe",
    "Straße", "heiß", "Größe", "außerdem", "Maße", "heißen", "schließen",
    "lösen", "prüfen", "führen", "fühlt", "möchte", "können", "würde",
]

# Eingefrorene Fachwort-Produktionswerte (Freeze c96bb4e, siehe
# tools/test_pronunciation_umlaut_ab.py::EXPECTED_C)
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


@pytest.fixture(scope="module")
def engine() -> PronunciationEngine:
    cfg = load_config()
    return PronunciationEngine(tech_germanization=bool(
        (cfg.get("german") or {}).get("tech_germanization", True)))


def _process(engine: PronunciationEngine, text: str):
    nr = NormalizationReport()
    normalized = normalize_text(text, "German", nr)
    return engine.process(normalized, "German", suggest_unknown=False)


def test_1_codepunkterhaltung_kompletter_nutzertext(engine):
    res = _process(engine, USER_TEST_TEXT)
    assert res.text == USER_TEST_TEXT
    for ch in "ÄÖÜäöüß":
        assert res.text.count(ch) == USER_TEST_TEXT.count(ch), ch
    assert res.replacements == []


def test_2_test_a_woerter_identity_keine_globale_substitution(engine):
    for w in TEST_A_WORDS:
        res = _process(engine, f"Bitte sprich {w} deutlich aus.")
        inner = res.text[len("Bitte sprich "):-len(" deutlich aus.")]
        assert inner == w, f"{w!r} wurde veraendert -> {inner!r}"
    # Expliziter ae/oe/ue/ss-Guard
    res = _process(engine, ", ".join(TEST_A_WORDS) + ".")
    for bad in ("Aepfel", "Baeume", "groesser", "groesste", "draussn",
                "Strasse", "weiss", "heiss", "Groesse", "huesch"):
        assert bad not in res.text, f"Transliteration {bad!r} im Output"


def test_3_fachwoerter_eingefroren(engine):
    for term, expected in EXPECTED_C.items():
        res = _process(engine, f"Thema: {term}.")
        inner = res.text[len("Thema: "):].rstrip(". ").strip()
        assert inner == expected, (
            f"Fachwort-Regression: {term!r} -> {inner!r}, erwartet "
            f"{expected!r}")


def test_4_umlaut_words_observability(engine):
    res = engine.process(USER_TEST_TEXT, "German", suggest_unknown=False)
    import re
    expected = sum(1 for w in re.findall(r"[A-Za-zÄÖÜäöüß]+",
                                         USER_TEST_TEXT)
                   if re.search(r"[äöüßÄÖÜ]", w))
    assert res.umlaut_words == expected
    assert res.umlaut_words > 30  # der Nutzertext ist umlautdicht


def test_5_pacing_hint_de_echte_umlautorthografie():
    from app.prosody.instruct import PACING_HINT_DE
    assert "natürlich" in PACING_HINT_DE
    assert "Sätzen" in PACING_HINT_DE
    assert "gleichmäßigen" in PACING_HINT_DE
    for bad in ("natuerlich", "Saetzen", "gleichmaessigen", "Erzaehlrhythmus"):
        assert bad not in PACING_HINT_DE


def test_6_umlautwoerter_sind_deutsch_wirkend():
    for w in ("Äpfel", "Bäume", "Türen", "Bücher", "größte", "Straße",
              "draußen", "Häuser", "müde", "weiß", "hörende"):
        assert _looks_german(w), w


def test_7_keine_risiko_fehlalarme_fuer_umlautwoerter(engine):
    res = engine.process(USER_TEST_TEXT, "German",
                         suggest_unknown=True, collect_meta=True)
    flagged = {u["term"] for u in res.unknown_problem_words}
    umlaut_false_positives = flagged & {
        "Äpfel", "Bäume", "Türen", "schöne", "Bücher", "Über", "Früher",
        "Bitte", "Besonders", "größer", "größte", "Straße", "Größe",
        "außerdem", "Hügel", "Vögel", "Häuser", "müde"}
    assert not umlaut_false_positives, (
        f"Normale deutsche (Umlaut-)Wörter fälschlich als riskante Namen "
        f"geflaggt: {sorted(umlaut_false_positives)}")


def test_8_satzanfang_kein_eigennamen_signal():
    mentions = scan_names("Über ihnen hängt eine große Lampe. "
                          "Bitte sprich deutlich.", set())
    names = {m.name for m in mentions}
    for w in ("Über", "Bitte"):
        assert w not in names, (
            f"{w!r} satzinitial faelschlich als Name geflaggt")


def test_9_wissenschaft_separat(engine):
    # Wissenschaft ist wiederkehrendes Akustik-Thema und bleibt als
    # Identity eingefroren; jede Änderung erfordert Host-A/B-Evidenz.
    for probe in ("Wissenschaft", "die Wissenschaft", "Wissenschaftler"):
        res = _process(engine, f"Thema: {probe}.")
        inner = res.text[len("Thema: "):-1].strip()
        assert probe in inner, f"{probe!r} veraendert -> {inner!r}"


def test_10_laengeres_segment_umlautkette(engine):
    # Punkt 8 des Auftrags: kurze UND längere Eingaben
    long_text = " ".join([USER_TEST_TEXT] * 4)
    res = _process(engine, long_text)
    assert res.text == long_text
    assert res.umlaut_words > 100
