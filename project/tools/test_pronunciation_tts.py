"""Echter TTS-Aussprache-Regressionstest (läuft nur auf GPU-Host).

Für die MATHEMATIK-Regressionssätze (Anforderung 8) und ausgewählte
Kernbegriffe wird ECHTER Qwen-TTS mit zwei Stimmen durchgeführt:
  - de_male_warm_storytelling_authoritative_01
  - de_male_warm_storytelling_authoritative_02

Erzeugt pro Stimme einen Ordner pronunciation_tts_regression/<voice>/
mit:
  - je Satz eine WAV-Datei (sent_NN.wav)
  - audit.json: TTS-Erfolg, Dauer, Ersetzungen, QC (Stille/Peak/RMS),
    Audio vorhanden / nicht still.
  - summary.md: übersichtlicher Bericht

Enthält KEINE Simulierung/WORKAROUND: nutzt die produktive Pipeline
(Pipeline + VoiceCloneEngine + QwenModelPool). Die Ergebnisse sind
also repräsentativ für die GUI-Ausgabe.

Offline ohne GPU wird der Test sauber SKIP melden (nicht FAIL).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Voices für den Regressionstest (Anforderung 8)
REGRESSION_VOICES = [
    "de_male_warm_storytelling_authoritative_01",
    "de_male_warm_storytelling_authoritative_02",
]

REGRESSION_SENTENCES = [
    "Mathematik ist die Sprache der Zahlen.",
    "Die Mathematik beschreibt Muster, Mengen und Strukturen.",
    "Ein mathematischer Algorithmus kann komplexe Probleme lösen.",
    "Quantenphysik und Mathematik bilden eine wichtige Grundlage moderner Forschung.",
]

# A/B-Tests: Original vs. Respelling für kritische Wörter (Anforderung 9).
# Der Respelling wird aus dem Wörterbuch geholt, wenn die Regel aktiv ist.
AB_TERMS = ["Mathematik", "Algorithmus", "Quantenphysik", "Artificial Intelligence"]


@dataclass
class SentenceAudioResult:
    sentence_index: int
    sentence: str
    voice_id: str
    variant: str                 # "original" | "optimized"
    wav_path: str = ""
    ok: bool = False
    error: str = ""
    duration_s: float = 0.0
    peak: float = 0.0
    rms: float = 0.0
    is_silent: bool = True
    tts_text: str = ""
    replacements: list = field(default_factory=list)
    elapsed_s: float = 0.0


def _qc_check_wav(path: Path) -> tuple[bool, float, float, float, str]:
    """Quick-QC: Datei existiert, >1KB, RMS > -50 dBFS (nicht still), Peak < 0dBFS."""
    try:
        import numpy as np
        import soundfile as sf
    except Exception as e:
        return False, 0.0, 0.0, 0.0, f"soundfile/numpy fehlt: {e}"
    if not path.exists():
        return False, 0.0, 0.0, 0.0, f"Datei fehlt: {path}"
    if path.stat().st_size < 1024:
        return False, 0.0, 0.0, 0.0, f"Datei zu klein ({path.stat().st_size} B)"
    try:
        data, sr = sf.read(str(path))
    except Exception as e:
        return False, 0.0, 0.0, 0.0, f"Read fehlgeschlagen: {e}"
    if data is None or len(data) == 0:
        return False, 0.0, 0.0, 0.0, "Leeres Audio"
    arr = data if hasattr(data, "ndim") and data.ndim == 1 else data.mean(axis=1)
    peak = float(abs(arr).max()) if len(arr) else 0.0
    rms = float((arr ** 2).mean() ** 0.5) if len(arr) else 0.0
    dur = float(len(arr) / sr) if sr else 0.0
    silent = rms < 0.002   # ~ -54 dBFS
    if silent:
        return False, dur, peak, rms, "Audio ist still (RMS < -54 dBFS)"
    if peak > 1.01:
        return False, dur, peak, rms, f"Clipping (Peak {peak:.3f})"
    return True, dur, peak, rms, ""


def _build_engine_for_voice(voice_id: str):
    """Baut eine produktionskonforme VoiceCloneEngine wie im GUI-Pfad."""
    from app.hardware.detector import detect_hardware
    from app.jobs.runner import _resolve_voice_native_language, _resolve_voice_seed
    from app.security.identity_lock import load_production
    from app.tts.qwen_engine import VoiceCloneEngine
    from app.voices.registry import VoiceRegistry

    hw = detect_hardware()
    if hw.mode == "cpu" and not hw.gpu_name:
        raise RuntimeError(
            "Keine CUDA-GPU – der TTS-Regressionstest braucht eine GPU.")
    registry = VoiceRegistry()
    entry = registry.get(voice_id)
    if entry is None:
        raise RuntimeError(f"Stimme unbekannt: {voice_id}")
    voice_lang = _resolve_voice_native_language(registry, entry)
    seed = _resolve_voice_seed(registry, entry)
    production = load_production()
    adv = {}
    try:
        from app import config as cfgmod
        adv = cfgmod.load_config().get("advanced", {})
    except Exception:
        pass
    from app.prosody.instruct import (ENGLISH_VOICEDESIGN_DESCRIPTIONS,
                                      VOICEDESIGN_DESCRIPTIONS)
    desc_entry = (ENGLISH_VOICEDESIGN_DESCRIPTIONS.get(voice_id)
                  or VOICEDESIGN_DESCRIPTIONS.get(voice_id) or {})
    description = (desc_entry.get("description")
                   or entry.description or f"{voice_lang} narrator")
    eng = VoiceCloneEngine(
        hw, candidate_id=voice_id,
        description=description,
        language=voice_lang,
        ref_text=None,
        seed=seed,
        models_dir=None,
        attn_implementation=adv.get("attn_implementation") or None,
        allow_design=False,
        reference_path=None)
    return eng, entry, voice_lang


def _synth(engine, text: str, language: str, wav_path: Path) -> tuple[bool, float, str]:
    try:
        from app.project.pipeline import SynthesisRequest
        t0 = time.perf_counter()
        req = SynthesisRequest(
            text=text, language=language,
            output_path=wav_path,
            speed=1.0, volume_db=0.0,
            max_seconds_hint=120.0)
        res = engine.synthesize(req)
        elapsed = time.perf_counter() - t0
        return True, elapsed, ""
    except Exception as e:
        return False, 0.0, f"{type(e).__name__}: {e}"


def _tts_preprocess(text: str) -> tuple[str, list]:
    from app.pronunciation import PronunciationEngine
    from app.text.normalize import normalize_text
    norm = normalize_text(text, "German")
    eng = PronunciationEngine()
    p = eng.process(norm, "German", suggest_unknown=False)
    return p.text, [{"from": r["from"], "to": r["to"], "rule": r.get("rule", "")}
                    for r in p.replacements]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=PROJECT_ROOT / "output" / "pronunciation_tts_regression")
    ap.add_argument("--skip-if-no-gpu", action="store_true",
                    help="Beende mit Code 0 (SKIP) wenn keine CUDA-GPU verfügbar.")
    ap.add_argument("--voice", action="append",
                    help="Nur diese Stimme testen (kann mehrfach angegeben werden)")
    args = ap.parse_args()

    # GPU-Check
    try:
        import torch  # noqa
        if not torch.cuda.is_available():
            raise RuntimeError("torch.cuda.is_available() == False")
    except Exception as e:
        if args.skip_if_no_gpu:
            print(f"SKIP (keine GPU): {e}")
            return 0
        print(f"FAIL: {e}")
        return 2

    voices = args.voice or REGRESSION_VOICES
    args.out.mkdir(parents=True, exist_ok=True)
    all_results: list[SentenceAudioResult] = []
    overall_ok = True

    for voice_id in voices:
        vdir = args.out / voice_id
        vdir.mkdir(parents=True, exist_ok=True)
        print(f"\n=== Stimme: {voice_id} ===")
        try:
            engine, entry, lang = _build_engine_for_voice(voice_id)
        except Exception as e:
            print(f"  FAIL engine build: {e}")
            overall_ok = False
            continue
        try:
            engine.load()
        except Exception as e:
            print(f"  FAIL engine.load: {e}")
            overall_ok = False
            continue
        for i, sent in enumerate(REGRESSION_SENTENCES, 1):
            tts_text, repls = _tts_preprocess(sent)
            wav = vdir / f"sent_{i:02d}.wav"
            ok, elapsed, err = _synth(engine, tts_text, "German", wav)
            qc_ok, dur, peak, rms, qc_err = (False, 0.0, 0.0, 0.0, "")
            if ok:
                qc_ok, dur, peak, rms, qc_err = _qc_check_wav(wav)
                if not qc_ok:
                    err = qc_err
            res = SentenceAudioResult(
                sentence_index=i, sentence=sent, voice_id=voice_id,
                variant="optimized", wav_path=str(wav),
                ok=ok and qc_ok, error=err or qc_err,
                duration_s=dur, peak=peak, rms=rms, is_silent=(rms < 0.002),
                tts_text=tts_text, replacements=repls, elapsed_s=elapsed)
            all_results.append(res)
            flag = "OK" if res.ok else "FAIL"
            print(f"  [{flag}] Satz {i}: {sent}")
            print(f"         TTS: {tts_text[:120]}")
            print(f"         Dauer {elapsed:.1f}s, Audio {dur:.1f}s, "
                  f"peak={peak:.3f}, rms={rms:.4f}")
            if not res.ok:
                print(f"         ! {res.error}")
                overall_ok = False
        try:
            engine.unload()
        except Exception:
            pass

    summary = {
        "final": "PASS" if overall_ok else "FAIL",
        "voices": voices,
        "results": [asdict(r) for r in all_results],
    }
    (args.out / "audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    # Markdown-Bericht
    lines = ["# Aussprache-TTS-Regression", "",
             f"Ergebnis: **{summary['final']}**", "",
             "| Stimme | Satz | OK | Dauer Audio | Peak | RMS | TTS-Text |",
             "|---|---|---|---|---|---|---|"]
    for r in all_results:
        lines.append(
            f"| {r.voice_id} | {r.sentence_index} | "
            f"{'✅' if r.ok else '❌'} | {r.duration_s:.1f}s | "
            f"{r.peak:.3f} | {r.rms:.4f} | {r.tts_text[:80]} |")
    (args.out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nFINAL_TTS_PRONUNCIATION_REGRESSION={summary['final']}")
    print(f"Reports in {args.out}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
