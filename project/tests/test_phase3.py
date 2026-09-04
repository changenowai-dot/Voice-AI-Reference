"""Phase-3-Tests: Referenz-erhaltende VD-E-Optimierung (§19–24).

Prüfstand: TestDoubleVoiceStudio. Die akustische Bewertung der Varianten
auf der RTX 5060:
    python app/main.py --phase3-run [--quick]
    python app/main.py --phase3-pick X
    python app/main.py --phase3-apply
"""
from __future__ import annotations

import json
from pathlib import Path

from app import paths
from app.tts.voice_studio import TestDoubleVoiceStudio


def _studio():
    return TestDoubleVoiceStudio()


# ---------------------------------------------------------------------------
# §20: Fremd-/Fachwörter (höchste Priorität)
# ---------------------------------------------------------------------------
def test_tech_terms_user_reported():
    from app.pronunciation import PronunciationEngine
    eng = PronunciationEngine()
    out = eng.process("Die Quantentheorie und jede Theorie bleiben. Das "
                      "Kybalion auch.", "German").text
    assert "Quan-ten-teo-RIE" in out            # Nutzer-Nennung §20
    assert "teo-RIE" in out
    assert "Kü-BA-li-on" in out
    assert "Quantentheorie" not in out and "Theorie" not in out.replace(
        "teo-RIE", "")


def test_tech_terms_do_not_touch_english_words():
    from app.pronunciation.tech_terms import apply_tech_germanization
    text = "Der Thriller war ein Hit."
    out, _ = apply_tech_germanization(text, "German")
    assert "Thriller" in out                    # echtes Englisch bleibt
    # englischer Satz: keine Germanisierung
    out2, _ = apply_tech_germanization("The theory of everything.", "English")
    assert out2 == "The theory of everything."


def test_tech_suffix_rule_for_compounds():
    from app.pronunciation.tech_terms import apply_tech_germanization
    out, repls = apply_tech_germanization(
        "Die Feldtheorie und die Eichtheorie folgen.", "German")
    assert "teo-RIE" in out
    assert any(r["rule"] == "tech_suffix" for r in repls)


def test_tech_priority_user_over_tech():
    from app.pronunciation import PronunciationDictionary, PronunciationEngine
    d = PronunciationDictionary()
    d.clear_all()
    d.add_entry("Entropie", "en-tro-PIE-eh")
    eng = PronunciationEngine(d)
    out = eng.process("Die Entropie wächst.", "German").text
    assert "en-tro-PIE-eh" in out               # Benutzer gewinnt (§8/§14)


def test_tech_uncovered_terms_reported_not_guessed():
    from app.pronunciation import PronunciationEngine
    eng = PronunciationEngine()
    res = eng.process("Die Dissonanzforschung bleibt unerwähnt.", "German",
                      suggest_unknown=True, collect_meta=True)
    flagged = [u["term"] for u in res.unknown_problem_words]
    assert any("Dissonanz" in f for f in flagged)   # gemeldet, nicht geraten


def test_tech_germanization_original_untouched():
    """§15: Originaltext bleibt – Respellings nur TTS-intern."""
    from app.pronunciation import PronunciationEngine
    original = "Die Quantentheorie bleibt vorläufig."
    eng = PronunciationEngine()
    tts = eng.process(original, "German").text
    assert original == "Die Quantentheorie bleibt vorläufig."   # unverändert
    assert tts != original                                       # TTS-Version


# ---------------------------------------------------------------------------
# §21: subtile Emotion (inhaltsausgelöst, nicht global)
# ---------------------------------------------------------------------------
def test_subtle_emotion_triggers():
    from app.prosody.variation import detect_subtle_emotion
    cases = {
        "Was aber, wenn diese Frage richtig gestellt war?": "curious",
        "Sogenannte Gewissheit, behaupten sie.": "skeptical",
        "Etwas Dunkles begann, sich zu recken.": "menace",
        "Und dann wird klar, worum es wirklich ging.": "realization",
        "Vielleicht irren wir uns auch hier.": "doubtful",
        "Unendlich viele Galaxien, und jede ein Gedanke.": "awe",
    }
    for text, want in cases.items():
        em, inten = detect_subtle_emotion(text)
        assert em == want and inten >= 2, (text, em, inten)
    # neutraler Satz: KEINE Emotion (nicht global emotionalisieren)
    em0, i0 = detect_subtle_emotion("Der Zug hält am Bahnhof.")
    assert em0 is None and i0 == 0


def test_subtle_emotion_never_fires_for_german_war():
    """Phase-3-Fix: deutsches „war“ löst KEINE somber-Emotion aus."""
    from app.prosody.instruct import detect_emotion
    em, _ = detect_emotion("Was aber, wenn diese Frage richtig gestellt war?")
    assert em == "neutral"


def test_subtle_emotion_budget_limited():
    from app.prosody import build_instruct
    t = "Was aber, wenn diese Frage richtig gestellt war?"
    with_hint = build_instruct("x", t, "German", german_variant="de_doc_native",
                               seg_index=4, last_high_idx=None)
    blocked = build_instruct("x", t, "German", german_variant="de_doc_native",
                             seg_index=4, last_high_idx=3)
    assert "curiosity" in with_hint
    assert "curiosity" not in blocked           # §7 Budget greift


# ---------------------------------------------------------------------------
# §22: Variation + §19.7 semantische Betonung
# ---------------------------------------------------------------------------
def test_role_sampling_offsets_subtle():
    from app.prosody.variation import (apply_sampling_offsets,
                                       sampling_offsets)
    base = {"temperature": 0.7, "top_k": 50}
    off = sampling_offsets("rhetorical_question", "curious", 2, "subtle")
    varied = apply_sampling_offsets(base, off)
    assert varied["temperature"] > base["temperature"]
    assert varied["temperature"] <= 0.92          # Referenz-erhaltend (§23)
    # neutrale Rolle ohne Emotion: keine Änderung
    none = sampling_offsets("statement", None, 0, "subtle")
    assert none == {}
    # strength aus -> keine Änderung
    assert sampling_offsets("dramatic", None, 0, "off") == {}


def test_emphasis_targets_semantic():
    from app.prosody.variation import emphasis_targets
    t = "besitzt den Schlüssel nicht zu einem Geheimnis, sondern zum " \
        "Bauplan der Wirklichkeit selbst"
    targets = emphasis_targets(t)
    assert len(targets) <= 2
    assert "Bauplan" in targets or "Wirklichkeit" in targets
    assert emphasis_targets("Er sprach nie darüber.") == ["nie"]


def test_variation_report_detects_monotony():
    import numpy as np
    from app.prosody.variation import variation_report
    sr = 24000
    # identische Tonhöhe über 4 "Segmente" -> Monotonie-Flag
    t = np.linspace(0, 1.5, int(1.5 * sr), dtype=np.float32)
    flat = [ (0.4 * np.sin(2 * np.pi * 150 * t)).astype(np.float32)
             for _ in range(4)]
    rep_flat = variation_report(flat, [sr] * 4, [0.5] * 4)
    assert rep_flat.get("f0_monotone") is True or rep_flat.get(
        "pauses_identical") is True
    # wechselnde Tonhöhen + Pausen -> variiert
    varied = [(0.4 * np.sin(2 * np.pi * f * t)).astype(np.float32)
              for f in (120, 150, 185, 135)]
    rep_var = variation_report(varied, [sr] * 4, [0.3, 0.5, 0.4, 0.8])
    assert not rep_var.get("f0_monotone", False)


# ---------------------------------------------------------------------------
# §23: Referenz-Schutz
# ---------------------------------------------------------------------------
def test_reference_locked_and_preserved():
    from app.benchmark.phase3 import ensure_reference, reference_f0, \
        reference_path
    ref = ensure_reference(_studio())
    assert ref.exists() and ref.name == "VD-E.wav"
    lock = json.loads((paths.BENCHMARK_DIR / "phase3" /
                       "reference_lock.json").read_text(encoding="utf-8"))
    import hashlib
    h = hashlib.sha256(ref.read_bytes()).hexdigest()
    assert lock["sha256"] == h
    assert lock["candidate_id"] == "VD-E"
    # zweiter Aufruf verändert die Referenz NICHT (Hash stabil)
    before = ref.read_bytes()
    ensure_reference(_studio())
    assert ref.read_bytes() == before
    assert reference_f0(ref) is not None


def test_voice_guard_band():
    from app.benchmark.phase3 import F0_BAND, run_phase3
    rep = run_phase3(_studio(), quick=True)
    for vid, r in rep["variants"].items():
        assert "voice_guard_ok" in r
        # Prüfstand erzeugt identische Stimme -> Guard muss OK sein
        assert r["voice_guard_ok"] is True, (vid, r["f0_median"],
                                             r["reference_f0"])


# ---------------------------------------------------------------------------
# Phase-3-Vergleich (Mechanik)
# ---------------------------------------------------------------------------
def test_phase3_run_structure():
    from app.benchmark.phase3 import run_phase3
    rep = run_phase3(_studio(), quick=True)
    ids = set(rep["variants"])
    assert ids == {"BASE", "TECH", "VAR", "TECHVAR"}
    for vid, r in rep["variants"].items():
        assert set(r["batteries"]) >= {"TECH", "EMOTION", "VARIATION",
                                       "MELODY"}
        assert r["composite"] > 0
    assert (paths.BENCHMARK_DIR / "phase3" / "comparisons" /
            "report_phase3.md").exists()
    blind = sorted((paths.BENCHMARK_DIR / "phase3" / "blind").glob(
        "sample_*.wav"))
    assert len(blind) == 4
    # TECH-Variante enthält germanisierte TTS-Texte
    assert (paths.BENCHMARK_DIR / "phase3" / "voicedesign" / "TECH" /
            "TECH" / "00.wav").exists()


def test_phase3_tech_battery_uses_germanization():
    from app.benchmark.phase3 import _kybalion_tts_texts
    off = " ".join(_kybalion_tts_texts(False))
    on = " ".join(_kybalion_tts_texts(True))
    assert "teo-RIE" not in off
    assert "teo-RIE" in on or "Kü-BA-li-on" in on


def test_phase3_pick_and_apply_only_switches():
    from app.benchmark.phase3 import (apply_phase3_pick, phase3_status,
                                      run_phase3, save_phase3_pick)
    from app import config as cfgmod
    pick_file = paths.BENCHMARK_DIR / "phase3" / "blind" / "user_pick.json"
    if pick_file.exists():
        pick_file.unlink()
    run_phase3(_studio(), quick=True)
    st = phase3_status()
    assert st["has_run"] and not st["picked"]
    assert st["mapping"] is None                    # verdeckt bis Auswahl
    letters = st["samples"]
    try:
        save_phase3_pick("X")
        raised = False
    except ValueError:
        raised = True
    assert raised
    st2 = save_phase3_pick(letters[0])
    variant = st2["mapping"][letters[0]]
    before = cfgmod.load_config()
    res = apply_phase3_pick()
    after = cfgmod.load_config()
    assert res["ok"]
    # §23: Stimme bleibt VD-E, nur Schalter ändern sich
    assert after["german"]["engine_mode"] == "voicedesign"
    assert after["german"]["voicedesign"]["candidate_id"] == "VD-E"
    assert after["german"]["tech_germanization"] == (
        variant in ("TECH", "TECHVAR"))
    assert after["german"]["variation"]["enabled"] == (
        variant in ("VAR", "TECHVAR"))
    cfgmod.save_config(before)                      # Testumgebung zurück


def test_phase3_variation_in_pipeline_clone_default():
    """Clone-Stimmen erhalten Sampling-Variation per Default (§22)."""
    from app.project.pipeline import _variation_enabled
    from app.tts.test_double import TestDoubleEngine

    class FakeClone(TestDoubleEngine):
        name = "qwen3-tts-clone"
    assert _variation_enabled({"german": {}}, FakeClone()) is True
    assert _variation_enabled({"german": {}}, TestDoubleEngine()) is False
    assert _variation_enabled(
        {"german": {"variation": {"enabled": True}}}, TestDoubleEngine()) \
        is True
    assert _variation_enabled(
        {"german": {"variation": {"enabled": False}}}, FakeClone()) is False


def test_phase3_api_end2end():
    import os
    import subprocess
    import sys
    import time
    import urllib.request
    port = 8803
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve().parent.parent /
                             "app" / "main.py"),
         "--webserver", "--engine", "test_double", "--no-browser",
         "--port", str(port)],
        env=dict(os.environ), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT)
    try:
        base = f"http://127.0.0.1:{port}"

        def get(p):
            return json.loads(urllib.request.urlopen(base + p,
                                                     timeout=30).read())

        def post(p, payload):
            req = urllib.request.Request(
                base + p, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=60).read())

        for _ in range(60):
            try:
                get("/api/status")
                break
            except Exception:
                time.sleep(0.5)
        assert post("/api/phase3/run", {"quick": True})["ok"]
        deadline = time.time() + 300
        while time.time() < deadline:
            s = get("/api/status")
            if not s["running"]:
                break
            time.sleep(1.0)
        st = get("/api/phase3/status")
        assert st["has_run"] and len(st["samples"]) == 4
        raw = urllib.request.urlopen(
            base + "/files/benchmark/phase3/blind/sample_"
            + st["samples"][0] + ".wav", timeout=30).read()
        assert raw[:4] == b"RIFF"
        assert post("/api/phase3/blind_pick",
                    {"letter": st["samples"][0]})["ok"]
        assert post("/api/phase3/apply", {})["ok"]
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
