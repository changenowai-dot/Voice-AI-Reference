"""Phase-1-Tests: deutsche Qualität (GERMAN-01 … GERMAN-10 + Baseline/A-B).

Jeder Test ist reproduzierbar (deterministische Texte/Seeds/Engines).
Die Tests laufen mit der TestDouble-Engine (Prüfstand) – die AKUSTISCHE
Validierung auf echter Hardware übernehmen:
    python app/main.py --german-baseline   (Baseline, §5)
    python app/main.py --german-ab         (A/B, §25)
    python app/main.py --german-speakers   (Stimmen, §19)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from app import paths
from app.benchmark.german_texts import GERMAN_TEXTS, texts_for_ids
from app.config import DEFAULT_CONFIG


# ---------------------------------------------------------------------------
# Unit: deutsche Normalisierung (§12)
# ---------------------------------------------------------------------------
def test_german_numbers_priority_list():
    """Die explizit geforderten Zahlen/Jahreszahlen (§12)."""
    from app.text.normalize import NormalizationReport, normalize_text

    def n(t):
        return normalize_text(t, "German", NormalizationReport())

    assert "neunzehnhundertvierzehn" in n("1914")
    assert "neunzehnhundertneununddreißig" in n("1939")
    assert "neunzehnhundertfünfundvierzig" in n("1945")
    assert "neunzehnhundertneunundachtzig" in n("1989")
    assert "zweitausendeins" in n("2001")           # NICHT „zweitausendein“
    assert "zweitausendsechsundzwanzig" in n("2026")
    assert "zehn" in n("10")
    assert "einhundert" in n("100")
    assert "eintausend" in n("1.000")
    assert "eintausendfünfhundert" in n("1.500")     # Menge, kein Jahr
    assert "drei Komma eins vier" in n("3,14")
    assert "fünfzig Prozent" in n("50 %")
    assert "zwei Komma fünf Prozent" in n("2,5 %")
    assert "zwanzigste Jahrhundert" in n("das 20. Jahrhundert")
    assert "dritte Jahrtausend" in n("das 3. Jahrtausend")


def test_german_ordinal_and_milliarde():
    from app.text.normalize import NormalizationReport, normalize_text

    def n(t):
        return normalize_text(t, "German", NormalizationReport())

    assert "der Vierzehnte" in n("Ludwig XIV.")
    assert "der Sechzehnte" in n("Benedikt XVI.")
    assert "fünf Milliarden" in n("5 Mrd.")
    assert "zwei Millionen" in n("2 Mio. Menschen")
    assert "eine Milliarde" in n("1 Mrd. Euro")
    assert "Paragraph zwölf" in n("§ 12")


# ---------------------------------------------------------------------------
# Unit: Aussprache (§8–11)
# ---------------------------------------------------------------------------
def test_names_detection_and_flagging():
    from app.pronunciation.dictionary import PronunciationDictionary
    from app.pronunciation.names import (risky_unknown_names,
                                         scan_names)
    d = PronunciationDictionary()
    d.clear_all()
    text = ("Descartes traf Göbekli Tepe-Forscher; später kam Zzyzx und "
            "ein unbekannter Qwrtz vorbei. Nietzsche lächelte.")
    names = scan_names(text, d.active_terms("German"))
    found = {m.name for m in names}
    assert "Descartes" in found and "Göbekli Tepe" in found
    assert "Nietzsche" in found
    risky = {m.name for m in risky_unknown_names(names)}
    assert "Qwrtz" in risky or "Zzyzx" in risky
    # Nietzsche ist durch Built-in abgedeckt -> nicht riskant-offen
    assert "Nietzsche" not in risky


def test_foreign_words_context_decision():
    from app.pronunciation.dictionary import PronunciationDictionary
    from app.pronunciation.engine import PronunciationEngine
    d = PronunciationDictionary()
    d.clear_all()
    eng = PronunciationEngine(d)
    # Anglizismus im deutschen Satz -> deutsche Realisierung
    res = eng.process("Das Meeting wurde verschoben.", "German",
                      collect_meta=True)
    assert "Mieting" in res.text
    # echte englische Phrase (3+ Wörter) -> unangetastet
    res2 = eng.process("Er sagte: The quick brown fox jumps.", "German",
                       collect_meta=True)
    assert "The quick brown fox" in res2.text
    # Absorbiertes Wort -> keine Ersetzung
    res3 = eng.process("Der Computer läuft.", "German", collect_meta=True)
    assert "Computer" in res3.text


def test_dictionary_extended_format():
    from app.pronunciation import PronunciationDictionary
    d = PronunciationDictionary()
    d.clear_all()
    # exakte Schreibweise: nur exakt matchen
    d.add_entry("IDS", {"de": "ii-de-es", "match": "exact"})
    t, _ = d.apply_to_text("ids bleibt, IDS nicht.", "German")
    assert "ids" in t and "ii-de-es" in t
    # Alternative schützt vor Doppeltersetzung
    d.clear_all()
    d.add_entry("Beispiel", {"de": "Bei-spiel", "alt": ["Bei-spiel"]})
    t2, _ = d.apply_to_text("Beispiel Beispiel", "German")
    assert t2.count("Bei-spiel") == 2
    # Sprachtrennung der Built-ins (Phase-1-Fix)
    t3, _ = d.apply_to_text("Nietzsche im deutschen Text.", "German")
    assert "Nietzsche" in t3            # DE-Built-in = Identität
    t4, _ = d.apply_to_text("Nietzsche in English text.", "English")
    assert "Nee-chuh" in t4             # EN-Built-in = Aussprachehilfe


def test_pronunciation_priority_user_overrides():
    from app.pronunciation import PronunciationDictionary
    d = PronunciationDictionary()
    d.clear_all()
    d.add_entry("ChatGPT", "tschatt-dschie-pie-tsie")
    t, _ = d.apply_to_text("ChatGPT im Satz.", "German")
    assert "tschatt-dschie-pie-tsie" in t.lower()   # Satzanfang kapitalisiert


# ---------------------------------------------------------------------------
# Unit: deutsche Prosodie (§13–16)
# ---------------------------------------------------------------------------
def test_german_sentence_roles():
    from app.prosody.german import profile_sentence
    assert profile_sentence(
        "Warum bleiben Menschen Muster?").role == "rhetorical_question"
    assert profile_sentence(
        "Ist das wirklich wahr?").role in ("question", "rhetorical_question")
    assert profile_sentence(
        "Erst kam A, dann B, schließlich C.").role == "list"   # §6: LIST
    assert profile_sentence("Er blieb, aber sie ging.").role == "contrast"
    assert profile_sentence("Dann kam die Stille.").role == "dramatic"


def test_german_instruct_variants_and_identity():
    from app.prosody import INSTRUCT_VARIANTS, build_instruct, variant_text
    from app.prosody.instruct import DEFAULT_GERMAN_VARIANT
    # Varianten vorhanden + unterschiedlich (kein Adjektiv-Klon)
    texts = [v["text"] for v in INSTRUCT_VARIANTS.values()]
    assert len(set(texts)) == len(texts)
    assert DEFAULT_GERMAN_VARIANT in INSTRUCT_VARIANTS
    base = variant_text("de_doc_native")
    assert "native German" in base and "never English prosody" in base
    # Sprachidentität: „German accent“ ist verboten (§16)
    for v in INSTRUCT_VARIANTS.values():
        assert "German accent" not in v["text"]
    # Frage-Hinweis erscheint
    instr = build_instruct("stil", "Warum passierte das?", "German",
                           german_variant="de_doc_native")
    assert "rhetorical question" in instr or "question" in instr
    # Konsistenz-Anker immer da
    assert "consistent" in instr


def test_pause_types_german():
    from app.prosody.german import PAUSE_BASE_DE
    from app.prosody.pauses import assign_pauses
    from app.segmentation import Segment
    # Absatz-Design: Satz a und b im Block 0, c folgt aus Block 1
    q = Segment(index=0, text="Warum wiederholen Menschen Muster?")
    a = Segment(index=1, text="Das ist eine einfache Aussage mit Inhalt.",
                block_index=0)
    b = Segment(index=2, text="Noch ein Satz im selben Absatz hier.",
                block_index=0)
    c = Segment(index=3, text="Ein Satz aus dem nächsten Absatz.",
                block_index=1)
    dram = Segment(index=4, text="Dann kam die Stille.")
    segs = [q, a, b, c, dram]
    for s_ in segs:
        s_.pause_after_s = 0.5
    assign_pauses(segs, style="auto")
    assert q.pause_type == "rhetorical_question"
    assert q.pause_after_s > a.pause_after_s           # Frage > Aussage
    assert dram.pause_after_s > a.pause_after_s        # dramatisch > Aussage
    assert b.pause_type == "paragraph"                 # Absatzgrenze danach
    assert b.pause_after_s > a.pause_after_s           # Absatz > Satzpause
    assert PAUSE_BASE_DE["rhetorical_question"] > PAUSE_BASE_DE["statement"]


# ---------------------------------------------------------------------------
# GERMAN-01…10: Textebene (deterministische Normalisierungs-Checks)
# ---------------------------------------------------------------------------
def _normalized(t):
    from app.text.normalize import NormalizationReport, normalize_text
    from app.pronunciation import PronunciationEngine
    rep = NormalizationReport()
    norm = normalize_text(t, "German", rep)
    return PronunciationEngine().process(norm, "German",
                                         collect_meta=True).text


def test_german_01_documentation():
    t = texts_for_ids(["GERMAN-01"])[0]["text"]
    out = _normalized(t)
    assert "neunzehnhundertvierunddreißig" in out
    assert "acht" in out
    assert "1934" not in out and "8" not in out.replace("acht", "")


def test_german_02_psychology():
    t = texts_for_ids(["GERMAN-02"])[0]["text"]
    out = _normalized(t)
    assert "neunzehnhundertfünfzehn" in out
    assert "Etätschment" in out            # Attachment deutsch realisiert
    assert "Bihejwer" in out               # Behavior deutsch realisiert
    assert "pü-che" in out.lower()         # Psyche


def test_german_03_years_numbers():
    t = texts_for_ids(["GERMAN-03"])[0]["text"]
    out = _normalized(t)
    for w in ("neunzehnhundertvierzehn", "neunzehnhundertneununddreißig",
              "neunzehnhundertfünfundvierzig",
              "neunzehnhundertneunundachtzig", "zweitausendeins",
              "zweitausendsechsundzwanzig", "zwanzigste Jahrhundert",
              "einhundert", "fünfzig Prozent", "Komma fünf"):
        assert w in out, w
    assert "1914" not in out


def test_german_04_names():
    t = texts_for_ids(["GERMAN-04"])[0]["text"]
    out = _normalized(t)
    # Namen aus Built-ins/respellings
    assert "Dekart" in out                 # Descartes
    assert "Göbäkli Tepe" in out           # Göbekli Tepe
    assert "der Vierzehnte" in out         # Ludwig XIV.


def test_german_05_foreign_words():
    t = texts_for_ids(["GERMAN-05"])[0]["text"]
    out = _normalized(t)
    for w in ("Mieting", "Dedlein", "Fidbek", "Dip Lörning",
              "Saikolodzi", "Meindset", "Tiem"):
        assert w in out, w
    assert "The quick brown fox jumps over the lazy dog" in out  # Phrase bleibt


def test_german_06_abbreviations():
    t = texts_for_ids(["GERMAN-06"])[0]["text"]
    out = _normalized(t)
    for w in ("unter anderem", "zum Beispiel", "vor allem", "und so weiter",
              "inklusive", "Doktor", "circa", "Uhr", "unter Umständen",
              "das heißt"):
        assert w in out, w


def test_german_07_long_sentence_kept_intact():
    t = texts_for_ids(["GERMAN-07"])[0]["text"]
    from app.segmentation import SegmentationConfig, segment_text
    from app.text.analyze import split_blocks
    segs = segment_text(split_blocks(t), lambda b: b.text,
                        SegmentationConfig(target_chars=420, max_chars=700))
    assert len(segs) >= 1
    # Langsatz wird an Nebensatzgrenzen geteilt, nie mitten im Wort
    words = set(t.split())
    joined = " ".join(s.text for s in segs)
    assert all(w in joined for w in words)


def test_german_08_rhetorical_questions():
    t = texts_for_ids(["GERMAN-08"])[0]["text"]
    from app.prosody import build_instruct
    from app.prosody.german import profile_sentence
    n_q = t.count("?")
    assert n_q >= 3
    # Instruct-Hinweis auf Segment-Ebene (Fragesatz als eigenes Segment)
    q_seg = "Warum wiederholen Menschen Muster, die sie längst durchschaut haben?"
    instr = build_instruct("s", q_seg, "German",
                           german_variant="de_doc_native")
    assert "rhetorical question" in instr
    assert profile_sentence(q_seg).role == "rhetorical_question"


def test_german_09_emotional():
    t = texts_for_ids(["GERMAN-09"])[0]["text"]
    from app.prosody import detect_emotion
    em, inten = detect_emotion(t)
    assert em in ("somber", "warm", "tense", "mysterious")
    assert inten >= 1


def test_german_10_longform_consistency():
    t = texts_for_ids(["GERMAN-10"])[0]["text"]
    from app.tts.engine_base import SynthesisRequest
    from app.tts.test_double import TestDoubleEngine
    from app.quality.german_score import score_german
    from app.segmentation import SegmentationConfig, segment_text
    from app.text.analyze import split_blocks
    segs = segment_text(split_blocks(t), lambda b: b.text,
                        SegmentationConfig(target_chars=300, max_chars=500))
    assert len(segs) >= 3
    eng = TestDoubleEngine()
    scores = []
    for i, s in enumerate(segs[:4]):
        res = eng.synthesize(SynthesisRequest(
            text=s.text, language="German", speaker="Ryan", seed=900 + i))
        g = score_german(res.waveform, res.sample_rate, s.text)
        scores.append(g.overall)
    assert all(s_ > 40 for s_ in scores)       # Prüfstand: Metrik aktiv


# ---------------------------------------------------------------------------
# GermanNaturalnessScore (§24) + QC-Härtung (§21)
# ---------------------------------------------------------------------------
def test_german_score_detects_defects():
    from app.quality.german_score import score_german
    sr = 24000
    t = "Warum wiederholen Menschen Muster, die sie längst durchschaut haben?"
    # defekt: Stille mit Frage
    silent = np.zeros(int(2.0 * sr), dtype=np.float32)
    g1 = score_german(silent, sr, t)
    assert g1.critical and g1.overall < 75 and "no_voiced_speech" in g1.issues
    # konstanter Ton (keine Sprachprosodie)
    tt = np.linspace(0, 2.5, int(2.5 * sr), dtype=np.float32)
    flat = (0.4 * np.sin(2 * np.pi * 150 * tt)).astype(np.float32)
    g2 = score_german(flat, sr, t)
    assert "monotone" in g2.issues or g2.prosody_de < 80
    # gesund (Prüfstand)
    from app.tts.test_double import TestDoubleEngine
    from app.tts.engine_base import SynthesisRequest
    res = TestDoubleEngine().synthesize(SynthesisRequest(
        text=t, language="German", speaker="Ryan"))
    g3 = score_german(res.waveform, res.sample_rate, t)
    assert g3.overall > 50


def test_qc_hard_rules_phase1():
    """85 Punkte sind NICHT automatisch gut genug (§21)."""
    from app.quality import SegmentQC
    from app.tts.engine_base import SynthesisRequest
    from app.tts.test_double import TestDoubleEngine
    qc = SegmentQC("German")
    res = TestDoubleEngine().synthesize(SynthesisRequest(
        text="Ein Testsatz mit ausreichend Inhalt für die Prüfung.",
        language="German", speaker="Ryan"))
    sc, _ = qc.check(res.waveform, res.sample_rate,
                     "Ein Testsatz mit ausreichend Inhalt für die Prüfung.")
    # kritisches Issue erzwingt Regeneration trotz hohem Score
    sc2, _ = qc.check(np.zeros(1200, dtype=np.float32), 24000,
                      "Ein Testsatz mit ausreichend Inhalt für die Prüfung.")
    assert sc2.critical and sc2.german is not None


def test_regeneration_targeted_changes():
    """Fehlerklasse bestimmt die Änderung; Varianten unterscheiden sich (§23)."""
    from app.quality import SegmentQC
    from app.quality.regeneration import attempt_changes, generate_with_qc
    from app.tts.engine_base import SynthesisRequest
    from app.tts.test_double import TestDoubleEngine

    base_sampling = {"temperature": 0.7, "top_k": 50, "top_p": 0.90,
                     "repetition_penalty": 1.05}
    # monotone -> Temperatur HOCH
    ch = attempt_changes(2, ["monotone"], base_sampling, "Base.")
    assert ch["sampling"]["temperature"] > base_sampling["temperature"]
    assert "melody" in ch["instruct"].lower()
    # Aussprache-Problem -> Temperatur NIEDRIG + Artikulations-Hinweis
    ch2 = attempt_changes(2, ["too_short"], base_sampling, "Base.")
    assert ch2["sampling"]["temperature"] < base_sampling["temperature"]
    assert "articulate" in ch2["instruct"].lower()
    # Fragen-Melodie -> gezielter Hinweis
    ch3 = attempt_changes(2, ["question_melody_missing"], base_sampling,
                          "Base.")
    assert "rising" in ch3["instruct"].lower()
    # Varianten sind unterschiedlich (Best-of-N nicht identisch)
    seen = set()
    for issues in (["monotone"], ["too_short"], ["mechanical_rhythm"]):
        c = attempt_changes(2, issues, base_sampling, "Base.")
        seen.add((c["sampling"]["temperature"], c["instruct"]))
    assert len(seen) == 3

    # Flaky-Engine: Versuch 1 defekt, Versuch 2 gut -> best = Versuch 2
    class Flaky(TestDoubleEngine):
        def __init__(self):
            super().__init__()
            self.calls = 0
        def synthesize(self, request):
            self.calls += 1
            if self.calls == 1:
                return type("R", (), {
                    "waveform": np.zeros(2400, dtype=np.float32),
                    "sample_rate": 24000, "duration_s": 0.1,
                    "elapsed_s": 0.01, "engine": "flaky",
                    "realtime_factor": 0.1, "params_used": {}})()
            return super().synthesize(request)

    text = "Die gezielte Regeneration wählt die beste Variante automatisch."
    out = generate_with_qc(Flaky(), SynthesisRequest(
        text=text, language="German", speaker="Ryan",
        sampling=dict(base_sampling)), text, SegmentQC("German"),
        max_attempts=3, min_score=70, min_german_score=40)
    assert out["best"].attempt == 2


# ---------------------------------------------------------------------------
# Baseline & A/B (§5, §25) – Mechanik mit Prüfstand-Engine
# ---------------------------------------------------------------------------
def test_baseline_protected_and_reproducible():
    from app.benchmark.german_ab import ensure_baseline
    from app.tts.test_double import TestDoubleEngine
    eng1, eng2 = TestDoubleEngine(), TestDoubleEngine()
    b1 = ensure_baseline(eng1, force=True)
    assert b1["n"] == len(GERMAN_TEXTS) and b1["n_failed"] == 0
    assert (paths.BENCHMARK_DIR / "baseline" / "manifest.json").exists()
    assert (paths.BENCHMARK_DIR / "baseline" / "report_baseline.md").exists()
    # zweiter Aufruf OHNE force: geschützt, identisch
    b2 = ensure_baseline(eng2, force=False)
    assert b2 == b1
    # Reproduzierbarkeit: gleiche Engine + Seeds -> gleicher Score
    b3 = ensure_baseline(eng1, force=True)
    assert b3["german_overall"] == b1["german_overall"]


def test_ab_uses_baseline_and_reports():
    from app.benchmark.german_ab import run_ab
    from app.tts.test_double import TestDoubleEngine
    rep = run_ab(TestDoubleEngine(), quick=True)
    assert (paths.BENCHMARK_DIR / "comparisons" / "report_AB.md").exists()
    assert len(rep["comparisons"]) >= 5
    assert rep["winner"]["instruct_variant"] in (
        "de_doc_classic", "de_doc_native", "de_audiobook", "de_psych",
        "de_restrained", "de_calm_authoritative", "de_cinematic",
        "de_lang_de")
    # Gewinner wurde in Konfiguration übernommen
    from app import config as cfgmod
    cfg = cfgmod.load_config()
    assert cfg["german"]["instruct_variant"] == rep["winner"][
        "instruct_variant"]
    # Audio vorhanden
    wavs = list((paths.BENCHMARK_DIR / "optimized").rglob("*.wav"))
    assert wavs


def test_german_speaker_benchmark_mechanics():
    from app.tts.test_double import TestDoubleEngine
    from app.voices.benchmark import run_german_speaker_benchmark
    rep = run_german_speaker_benchmark(TestDoubleEngine(),
                                        speakers=["Ryan", "Aiden",
                                                  "Serena"], quick=True)
    assert rep["best_male"] in ("Ryan", "Aiden")
    assert (paths.BENCHMARK_DIR / "german_speakers.md").exists()
    from app import config as cfgmod
    cfg = cfgmod.load_config()
    assert cfg["german"]["best_speaker"] == rep["best_german_narrator"]
    assert "speaker_map" in cfg["voices"]


# ---------------------------------------------------------------------------
# Regression: bestehende Funktionen unversehrt (§29)
# ---------------------------------------------------------------------------
def test_pipeline_full_german_with_phase1():
    from app.project.pipeline import Pipeline
    from app.tts.test_double import TestDoubleEngine
    import json as _json
    paths.INPUT_DIR.mkdir(parents=True, exist_ok=True)
    p = paths.INPUT_DIR / "phase1_test.txt"
    p.write_text(("Warum wiederholen Menschen Muster, die sie längst "
                  "durchschaut haben? Nietzsche notierte 1915 in einem "
                  "Meeting mit dem Team: 3,7 % der Antworten kamen von "
                  "ChatGPT. Doch die Frage bleibt.\n\nEin neuer Absatz "
                  "beginnt im 20. Jahrhundert."), encoding="utf-8")
    cfg = _json.loads(_json.dumps(DEFAULT_CONFIG))
    cfg["german"]["instruct_variant"] = "de_doc_native"
    cfg["advanced"]["segment_target_chars"] = 240
    rep = Pipeline(cfg, TestDoubleEngine()).process_file(p)
    assert rep["ok"], rep
    assert Path(rep["wav"]).exists() and Path(rep["mp3"]).exists()
    assert rep["segments"] >= 2
    assert rep["avg_score"] is not None
