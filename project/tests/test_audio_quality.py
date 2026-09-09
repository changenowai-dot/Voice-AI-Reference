"""Tests: Audio (WAV N, MP3 O, Normalisierung P), QC (L), Regeneration (M)."""
from __future__ import annotations

import numpy as np


def _sr() -> int:
    return 24000


def test_wav_roundtrip_all_depths():
    from app.audio.io import read_wav, write_wav
    from app import paths
    sr = _sr()
    t = np.linspace(0, 1, sr, dtype=np.float32)
    wav = 0.5 * np.sin(2 * np.pi * 220 * t).astype(np.float32)
    for depth in (16, 24):
        p = paths.CACHE_DIR / f"rt_{depth}.wav"
        write_wav(p, wav, sr, bit_depth=depth)
        back, sr2 = read_wav(p)
        assert sr2 == sr
        assert back.dtype == np.float32
        err = float(np.max(np.abs(back - wav)))
        assert err < 0.002, f"Roundtrip-Fehler {err} bei {depth} bit"


def test_lufs_measurement_sane():
    from app.audio.ebu_r128 import integrated_lufs, true_peak_dbtp
    sr = 48000
    t = np.linspace(0, 3, 3 * sr, dtype=np.float64)
    # Vollskala-Sinus liegt typischerweise um ca. -3 … -6 LUFS
    ref = 0.5 * np.sin(2 * np.pi * 997 * t)
    lufs = integrated_lufs(ref.astype(np.float32), sr)
    assert -15 < lufs < 0, lufs
    tp = true_peak_dbtp(ref.astype(np.float32), sr)
    assert -7 < tp < -5.5, tp
    # Stille
    assert integrated_lufs(np.zeros(sr, dtype=np.float32), sr) <= -69


def test_assemble_trims_and_pauses():
    from app.audio.assemble import assemble
    from app.segmentation import Segment
    sr = _sr()
    n = int(1.0 * sr)
    wav = np.zeros(n, dtype=np.float32)
    wav[1000:16000] = 0.5                   # Signal in der Mitte
    seg1 = Segment(index=0, text="a" * 50, pause_after_s=0.5)
    seg2 = Segment(index=1, text="b" * 50, pause_after_s=0.2)
    seg1.block_kind = seg2.block_kind = "paragraph"
    out, sr_out = assemble([(wav, sr, seg1), (wav, sr, seg2)])
    # Randstille gekürzt: deutlich kürzer als 2 s Signal + 0.7 s Pause
    assert len(out) / sr_out < 2.6
    assert len(out) / sr_out > 1.6
    # Pause vorhanden (Stille zwischen den Blöcken)
    mid = len(out) // 2
    assert float(np.max(np.abs(out[mid - 100:mid + 100]))) < 0.01


def test_master_youtube_targets():
    from app.audio.master import master_to_youtube
    from app import paths
    from app.audio.ebu_r128 import integrated_lufs
    from app.audio.io import read_wav
    sr = 48000
    t = np.linspace(0, 6, 6 * sr, dtype=np.float32)
    speech = (0.3 * np.sin(2 * np.pi * 140 * t) *
              (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))).astype(np.float32)
    wav_out = paths.OUTPUT_DIR / "master_test.wav"
    mp3_out = paths.OUTPUT_DIR / "master_test.mp3"
    rep = master_to_youtube(speech, sr, wav_out, mp3_out,
                            target_lufs=-14.0, true_peak_dbtp=-1.5)
    m, sr2 = read_wav(wav_out)
    lufs = integrated_lufs(m, sr2)
    assert abs(lufs - (-14.0)) <= 1.0, f"LUFS {lufs} außerhalb des Ziels"
    assert rep["lufs_out"] is not None
    if rep.get("ffmpeg"):
        assert mp3_out.exists() and mp3_out.stat().st_size > 1000
    else:
        # Fallback: WAV vorhanden, MP3 ggf. nicht (dokumentierte Grenze)
        assert wav_out.exists()


def test_qc_detects_defects():
    from app.quality import SegmentQC
    sr = _sr()
    qc = SegmentQC("German")
    text = "Dies ist ein Testsatz mit genau genug Inhalt für die Prüfung."

    # 1) zu kurz (Wörter verloren)
    short = np.zeros(int(0.2 * sr), dtype=np.float32)
    score1, _ = qc.check(short, sr, text)
    assert score1.overall < 70 and "too_short" in score1.issues

    # 2) Clipping
    t = np.linspace(0, 2.5, int(2.5 * sr), dtype=np.float32)
    clipped = np.clip(2.0 * np.sin(2 * np.pi * 150 * t), -1.0, 1.0)
    score2, m2 = qc.check(clipped.astype(np.float32), sr, text)
    assert "clipping" in score2.issues or score2.audio_integrity < 100

    # 3) monotone Internation (konstanter Ton)
    mono = (0.4 * np.sin(2 * np.pi * 150 * t)).astype(np.float32)
    score3, _ = qc.check(mono, sr, text)
    assert "monotone" in score3.issues and score3.prosody < 80

    # 4) gesunde Sprach-Simulation (TestDouble-Engine)
    from app.tts.test_double import TestDoubleEngine
    eng = TestDoubleEngine()
    from app.tts.engine_base import SynthesisRequest
    res = eng.synthesize(SynthesisRequest(
        text=text * 3, language="German", speaker="Ryan"))
    score4, m4 = qc.check(res.waveform, res.sample_rate, text * 3)
    assert score4.overall >= 70, score4.to_dict()
    # Phase 1: der deutsche Score meldet bei der Prüfstands-Engine
    # (konstanter Silbenpuls, keine echte Frage-Melodie) typische
    # Artefakte – zulässig hier, kritisch geprüft wird separat.
    allowed = {"mechanical_rhythm", "mechanical_pauses",
               "question_melody_missing"}
    assert not [i for i in score4.issues if i not in allowed], score4.issues


def test_qc_detects_long_internal_pause():
    from app.quality import SegmentQC
    from app.tts.test_double import TestDoubleEngine
    from app.tts.engine_base import SynthesisRequest
    eng = TestDoubleEngine()
    text = ("Ein langer Testsatz der genug Inhalt hat um die Prüfung zu "
            "bestehen und damit die Dauerplausibilität zu erfüllen ist hier "
            "schnell geschrieben und wird nochmal verlängert.")
    res = eng.synthesize(SynthesisRequest(text=text, language="German",
                                          speaker="Ryan"))
    wav = res.waveform.copy()
    mid = len(wav) // 2
    wav[mid:mid + int(2.8 * res.sample_rate)] *= 0.0    # 2,8 s Stille
    qc = SegmentQC("German")
    score, _ = qc.check(wav, res.sample_rate, text)
    assert "long_pause" in score.issues


def test_regeneration_picks_best_variant():
    from app.quality import SegmentQC
    from app.quality.regeneration import generate_with_qc
    from app.tts.engine_base import SynthesisRequest
    from app.tts.test_double import TestDoubleEngine

    class FlakyEngine(TestDoubleEngine):
        """Versuch 1: kaputt (zu kurz), danach: gut."""
        def __init__(self):
            super().__init__()
            self.calls = 0
        def synthesize(self, request):
            self.calls += 1
            if self.calls == 1:
                import numpy as np
                return type("R", (), {
                    "waveform": np.zeros(2400, dtype=np.float32),
                    "sample_rate": 24000, "duration_s": 0.1,
                    "elapsed_s": 0.01, "engine": "flaky",
                    "realtime_factor": 0.1, "params_used": {}})()
            return super().synthesize(request)

    eng = FlakyEngine()
    text = "Die Regeneration wählt automatisch die beste von mehreren Varianten."
    qc = SegmentQC("German")
    req = SynthesisRequest(text=text, language="German", speaker="Ryan")
    out = generate_with_qc(eng, req, text, qc, max_attempts=3, min_score=75)
    assert out["best"] is not None
    assert out["best"].attempt == 2                  # schlechter Versuch verworfen
    assert out["best"].score >= out["attempts"][0].score
    assert eng.calls == 2


def test_metrics_reasonable():
    from app.quality.metrics import analyze_segment_audio
    from app.tts.test_double import TestDoubleEngine
    from app.tts.engine_base import SynthesisRequest
    eng = TestDoubleEngine()
    res = eng.synthesize(SynthesisRequest(
        text="Ein Satz für die Metrikprüfung mit mehreren Wörtern.",
        language="German", speaker="Serena"))
    m = analyze_segment_audio(res.waveform, res.sample_rate)
    assert 0 < m["duration_s"] < 5
    assert m["f0_median_hz"] > 150          # Frauenstimmen-Simulation
    assert m["lufs"] > -40
    assert m["clip_ratio"] < 0.001
    assert m["silence_ratio"] < 0.4
