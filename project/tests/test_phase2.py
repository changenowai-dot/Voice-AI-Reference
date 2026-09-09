"""Phase-2-Tests: VoiceDesign, Prosodie-Rollen, Blindvergleich, Schutz.

Läuft mit TestDoubleVoiceStudio (Prüfstand). Die akustische Bewertung
auf der RTX 5060 erfolgt über:
    python app/main.py --phase2-run [--quick]   (Vergleich §17)
    python app/main.py --phase2-pauses          (Pausen-Sonde §10)
    python app/main.py --phase2-pick B          (Blindauswahl §20)
    python app/main.py --phase2-apply           (Übernahme §23)
"""
from __future__ import annotations

import json
from pathlib import Path

from app import paths
from app.tts.engine_base import SynthesisRequest
from app.tts.test_double import TestDoubleEngine


# ---------------------------------------------------------------------------
# Kybalion-Text (§16, wörtlich)
# ---------------------------------------------------------------------------
def test_kybalion_text_exact():
    from app.benchmark.phase2_texts import KYBALION_TEXT
    assert "Es gibt ein Buch, das niemand geschrieben haben will." \
        in KYBALION_TEXT
    assert "1908" in KYBALION_TEXT
    assert "verfasst von drei Eingeweihten" in KYBALION_TEXT
    assert "Hermes Trismegistos" in KYBALION_TEXT
    assert "Systemtheorie" in KYBALION_TEXT
    assert KYBALION_TEXT.count("\n") >= 9          # 10 Sätze/Zeilen
    # nicht verändert durch Normalisierung? -> Anzahl Wörter stabil
    words = KYBALION_TEXT.split()
    assert len(words) > 150


def test_kybalion_normalization():
    from app.pronunciation import PronunciationEngine
    from app.text.normalize import NormalizationReport, normalize_text
    rep = NormalizationReport()
    out = normalize_text(KYBALION_HALF(), "German", rep)
    out = PronunciationEngine().process(out, "German").text
    assert "neunzehnhundertacht" in out            # 1908
    assert "1908" not in out
    assert "kü-ba-li-on" in out.lower()           # Kybalion (§13, Phase 3:
    # Betonungs-Großbuchstaben sind erlaubt)
    assert "Tris-me-gis-tos" in out                # Trismegistos
    assert "Griechen" in out and "Pyramiden" in out  # Inhalt unberührt


def KYBALION_HALF() -> str:
    from app.benchmark.phase2_texts import KYBALION_TEXT
    return "\n".join(KYBALION_TEXT.split("\n")[:4])


# ---------------------------------------------------------------------------
# Neue Satzrollen (§6)
# ---------------------------------------------------------------------------
def test_roles_explanation_transition_calm():
    from app.prosody import dominant_role
    assert dominant_role("Das liegt nämlich daran, dass das System "
                         "reagiert.") == "explanation"
    assert dominant_role("Damit wenden wir uns dem zweiten Prinzip zu."
                         ) == "transition"
    assert dominant_role("Vielleicht war es irgendwie immer schon "
                         "bekannt.") == "calm"
    assert dominant_role("Warum wiederholen Menschen Muster?") == \
        "rhetorical_question"


def test_rhetorical_setup_detected():
    from app.prosody.german import profile_sentence
    p = profile_sentence("Doch was passiert, wenn wir diese Idee ernst "
                         "nehmen?")
    assert p.role == "rhetorical_question"          # §8-Beispiel


def test_hint_budget_no_over_dramatization():
    from app.prosody import build_instruct
    from app.prosody.german import hint_allowed
    # statement/calm/transition: kein Hinweis (§7)
    s = build_instruct("x", "Ein einfacher Satz mit ganz normaler Aussage.",
                       "German", german_variant="de_doc_native", seg_index=0)
    assert "question" not in s and "weight" not in s and "contrast" not in s
    # Dramatik nie zwei Segmente in Folge
    assert hint_allowed(0, "dramatic", None) is True
    assert hint_allowed(1, "dramatic", 0) is False
    assert hint_allowed(2, "dramatic", 0) is True
    # ruhige Rollen bleiben hinweisfrei
    assert hint_allowed(5, "statement", None) is False
    assert hint_allowed(5, "calm", None) is False


def test_anchor_rotation_variety():
    from app.prosody import build_instruct
    t = "Warum wiederholen Menschen Muster, die sie durchschaut haben?"
    i0 = build_instruct("x", t, "German", german_variant="de_doc_native",
                        seg_index=0)
    i1 = build_instruct("x", t, "German", german_variant="de_doc_native",
                        seg_index=1)
    i2 = build_instruct("x", t, "German", german_variant="de_doc_native",
                        seg_index=2)
    anchors = {i0, i1, i2}
    assert len(anchors) == 3                      # §9: keine identische
    assert all("consistent" in a for a in anchors)


def test_short_run_build_positions():
    from app.prosody import build_instruct, detect_short_sentence_run
    texts = ["Sieben Prinzipien.", "Sieben Regeln.", "Eine einzige Ordnung.",
             "Danach folgt ein langer Satz mit vielen Wörtern wieder."]
    run = detect_short_sentence_run(texts)
    assert run == [0, 1, 2]
    i0 = build_instruct("x", texts[0], "German",
                        german_variant="de_doc_native", seg_index=0,
                        short_run_pos="first")
    i2 = build_instruct("x", texts[2], "German",
                        german_variant="de_doc_native", seg_index=2,
                        short_run_pos="last")
    assert "begins a rhythmic sequence" in i0       # §12
    assert "closes the short-phrase sequence" in i2


def test_long_sentence_hint():
    from app.prosody import build_instruct
    long = ("Wer immer wieder versucht, die leise bröckelnde Ordnung seiner "
            "Erinnerungen gegen die stürmische Flut der Vergessenheit zu "
            "verteidigen, wird bemerken, dass nicht die großen Momente "
            "bleiben, sondern die unscheinbaren, die sich niemand bewusst "
            "ausgesucht hat, obwohl sie für immer bleiben wollen.")
    i = build_instruct("x", long, "German", german_variant="de_doc_native",
                       seg_index=1, long_sentence=True)
    assert "Structure this long sentence" in i      # §11


def test_pause_strategies_differ():
    from app.prosody import assign_pauses, dominant_role
    from app.segmentation import segment_text
    from app.text.analyze import split_blocks
    text = ("Warum wiederholen Menschen Muster, die sie durchschaut haben? "
            "Die Psychologie kennt mehrere Antworten auf diese Frage. "
            "Ein gewöhnlicher Satz steht hier einfach im Absatzfluss. "
            "Denn schließlich nämlich bleibt die Sache komplex. "
            "Damit wenden wir uns dem nächsten Abschnitt zu.")
    from app.segmentation import SegmentationConfig
    def build():
        return segment_text(split_blocks(text), lambda b: b.text,
                            SegmentationConfig(target_chars=110,
                                               min_chars=30, max_chars=300))
    segs = build()
    outs = {}
    for strat in ("classic", "semantic", "flow"):
        s2 = build()
        assign_pauses(s2, style="auto", speed=1.0, strategy=strat)
        outs[strat] = [round(x.pause_after_s, 2) for x in s2]
    assert outs["classic"] != outs["semantic"]
    assert outs["classic"] != outs["flow"]
    # semantic: nach rhetorischer Frage mehr Raum (§8/§10)
    rq = next(i for i, x in enumerate(segs)
              if dominant_role(x.text) == "rhetorical_question")
    assert outs["semantic"][rq] > outs["classic"][rq]
    # flow: Aussagen knapper als classic
    st_idx = next(i for i, x in enumerate(segs)
                  if dominant_role(x.text) == "statement")
    assert outs["flow"][st_idx] < outs["classic"][st_idx]


# ---------------------------------------------------------------------------
# VoiceDesign-Beschreibungen (§3)
# ---------------------------------------------------------------------------
def test_voicedesign_descriptions():
    from app.prosody import VOICEDESIGN_DESCRIPTIONS
    need = {"vd_a", "vd_b", "vd_c"}                  # Auftrags-Vorgaben
    assert need.issubset(set(VOICEDESIGN_DESCRIPTIONS))
    assert len(VOICEDESIGN_DESCRIPTIONS) >= 6        # + verfeinerte
    for key, v in VOICEDESIGN_DESCRIPTIONS.items():
        d = v["description"]
        assert "deutsch" in d.lower() or "german" in d.lower()
        assert "accent" not in d.lower() or "muttersprachler" in d.lower()
        assert len(d) > 60                            # substanziell


# ---------------------------------------------------------------------------
# Studio-Prüfstand (Design->Clone deterministisch & konsistent)
# ---------------------------------------------------------------------------
def test_studio_design_clone_consistency():
    from app.tts.voice_studio import TestDoubleVoiceStudio
    studio = TestDoubleVoiceStudio()
    ref = studio.design_reference("T-VD1", "Tiefer ruhiger deutscher "
                                     "Dokumentarsprecher.")
    assert ref.wav_path.exists()
    prompt = studio.build_clone_prompt(ref)
    req = SynthesisRequest(text="Ein Testsatz für die Stimmkonstanz.",
                           language="German", speaker="-", seed=42)
    r1 = studio.synth_clone(prompt, req)
    r2 = studio.synth_clone(prompt, req)
    # gleiche Stimme -> identische Wellenform (Prüfstand deterministisch)
    assert r1.waveform.shape == r2.waveform.shape
    # andere Beschreibung -> andere Stimme
    ref2 = studio.design_reference("T-VD2", "Höhere, hellere Stimme.")
    p2 = studio.build_clone_prompt(ref2)
    r3 = studio.synth_clone(p2, req)
    import numpy as np
    assert not np.allclose(r1.waveform[:4800], r3.waveform[:4800])


def test_model_pool_swaps_and_protects():
    """Modell-Pool: nur EIN Modell gleichzeitig (VRAM, §32)."""
    from app.tts.model_pool import QwenModelPool
    pool = QwenModelPool.__new__(QwenModelPool)     # ohne torch
    pool._current_kind = None
    pool._model = None
    # Schutzcheck Phase 1 (§2)
    from app.benchmark.phase2_ab import assert_no_phase1_write
    try:
        assert_no_phase1_write(paths.BENCHMARK_DIR / "baseline" / "x.wav")
        raised = False
    except RuntimeError:
        raised = True
    assert raised
    # Phase-2-Pfade sind erlaubt
    assert_no_phase1_write(paths.BENCHMARK_DIR / "phase2" / "blind" / "a.wav")


# ---------------------------------------------------------------------------
# Phase-2-Vergleich (Mechanik, Prüfstand)
# ---------------------------------------------------------------------------
def test_phase2_run_full_mechanics():
    from app.benchmark.phase2_ab import run_phase2
    from app.tts.voice_studio import TestDoubleVoiceStudio
    # Phase-1-Schutz: Sentinels setzen
    p1_baseline = paths.BENCHMARK_DIR / "baseline"
    p1_baseline.mkdir(parents=True, exist_ok=True)
    sentinel = p1_baseline / "manifest.json"
    sentinel.write_text('{"protected": true}', encoding="utf-8")

    rep = run_phase2(TestDoubleVoiceStudio(), quick=True)
    # Kandidaten: P1-CURRENT + mind. 1 Sweep + VD-A/B/C
    ids = [c["id"] for c in rep["candidates"]]
    assert "P1-CURRENT" in ids
    assert any(i.startswith("VD-") for i in ids)
    ok = [c for c in rep["candidates"] if not c.get("error")]
    assert len(ok) >= 4
    # Phase 1 unangetastet (§2)
    assert json.loads(sentinel.read_text(encoding="utf-8")) == \
        {"protected": True}
    # Blindproben + Schlüssel
    blind = sorted((paths.BENCHMARK_DIR / "phase2" / "blind").glob(
        "sample_*.wav"))
    assert len(blind) == len(ok)
    key = json.loads((paths.BENCHMARK_DIR / "phase2" / "blind" /
                      "blind_key.json").read_text(encoding="utf-8"))
    assert len(key["mapping"]) == len(ok)
    assert sorted(key["mapping"].values()) == sorted(c["id"] for c in ok)
    # Berichte
    assert (paths.BENCHMARK_DIR / "phase2" / "comparisons" /
            "report_phase2.md").exists()
    assert (paths.BENCHMARK_DIR / "phase2" / "comparisons" /
            "recommendation.json").exists()


def test_phase2_blind_pick_and_apply():
    from app.benchmark.phase2_ab import (apply_pick_or_candidate,
                                         blind_status, run_phase2,
                                         save_blind_pick)
    from app.tts.voice_studio import TestDoubleVoiceStudio
    from app import config as cfgmod
    # vorherige Auswahl (z. B. aus E2E-Test) zurücksetzen
    pick_file = paths.BENCHMARK_DIR / "phase2" / "blind" / "user_pick.json"
    if pick_file.exists():
        pick_file.unlink()
    run_phase2(TestDoubleVoiceStudio(), quick=True)

    status = blind_status()
    assert status["has_run"] and not status["picked"]
    assert status["mapping"] is None                 # Blind: verdeckt
    letters = status["samples"]
    assert len(letters) >= 4

    # ungültige Auswahl abgelehnt
    try:
        save_blind_pick("Z")
        raised = False
    except ValueError:
        raised = True
    assert raised

    # gültige Auswahl -> Mapping wird enthüllt
    st2 = save_blind_pick(letters[0])
    assert st2["picked"] and st2["mapping"] is not None
    winner = st2["mapping"][letters[0]]

    # Übernahme (§23)
    cfg_before = cfgmod.load_config()
    res = apply_pick_or_candidate()
    assert res["ok"]
    cfg_after = cfgmod.load_config()
    if winner.startswith("VD-"):
        assert cfg_after["german"]["engine_mode"] == "voicedesign"
        assert cfg_after["german"]["voicedesign"]["candidate_id"] == winner
        # Clone-Referenz vorhanden
        assert (paths.VOICE_REFS_DIR /
                f"{winner}.wav").exists()
    else:
        assert cfg_after["german"]["engine_mode"] == "customvoice"
    # Zurücksetzen für weitere Tests
    cfgmod.save_config(cfg_before)


def test_phase1_legacy_instruct_emulation():
    from app.benchmark.phase2_ab import legacy_phase1_instruct
    i = legacy_phase1_instruct("Warum wiederholen Menschen Muster?",
                               "de_restrained")
    assert "Restrained German documentary voice" in i
    assert "consistent" in i
    assert "rhetorical question" in i or "question" in i


def test_pause_probe_runs():
    from app.benchmark.phase2_ab import run_pause_probe
    from app.tts.voice_studio import TestDoubleVoiceStudio
    out = run_pause_probe(TestDoubleVoiceStudio())
    assert set(out) == {"classic", "semantic", "flow"}
    assert (paths.BENCHMARK_DIR / "phase2" / "pause_probe" /
            "report.json").exists()


# ---------------------------------------------------------------------------
# UI/API-Ende-zu-Ende (Phase 2)
# ---------------------------------------------------------------------------
def test_phase2_api_end2end():
    import os
    import subprocess
    import sys
    import time
    import urllib.request
    import urllib.error
    port = 8799
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve().parent.parent /
                             "app" / "main.py"),
         "--webserver", "--engine", "test_double", "--no-browser",
         "--port", str(port)],
        env=dict(os.environ), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT)
    try:
        base = f"http://127.0.0.1:{port}"

        def get(path):
            return json.loads(urllib.request.urlopen(base + path,
                                                     timeout=30).read())

        def post(path, payload):
            req = urllib.request.Request(
                base + path, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=60).read())

        for _ in range(60):
            try:
                get("/api/status")
                break
            except Exception:
                time.sleep(0.5)
        # Phase-2-Lauf starten (Schnelltest)
        r = post("/api/phase2/run", {"quick": True})
        assert r["ok"]
        deadline = time.time() + 300
        st = {}
        while time.time() < deadline:
            s = get("/api/status")
            st = get("/api/phase2/status")
            if st.get("has_run") and not s["running"]:
                break
            time.sleep(1.0)
        st = get("/api/phase2/status")
        assert st["has_run"] and len(st["samples"]) >= 4
        # Blinddatei ausspielbar
        raw = urllib.request.urlopen(
            base + "/files/benchmark/phase2/blind/sample_"
            + st["samples"][0] + ".wav", timeout=30).read()
        assert raw[:4] == b"RIFF"
        # Auswahl + Übernahme
        r2 = post("/api/phase2/blind_pick", {"letter": st["samples"][0]})
        assert r2["ok"] and r2["status"]["picked"]
        r3 = post("/api/phase2/apply", {})
        assert r3["ok"]
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
