"""Echter TTS-Regressionstest für Aussprache (Punkte 8/9 des Auftrags).

Synthetisiert die vier zentralen Regressionssätze über Qwen mit den
beiden geforderten Stimmen (de_male_warm_storytelling_authoritative_01
und de_male_warm_storytelling_authoritative_02) und schreibt
pro Satz WAV + JSON-Report inklusive Audiodauer, Elapsed-Time,
Sample-Rate, ob das Audio still ist (Peak/RMS) und welche
Aussprache-Ersetzungen vorgenommen wurden.

Offline/Sandbox-Umgebungen ohne CUDA beenden sauber mit SKIP.
"""
from __future__ import annotations

import json
import os
import sys
import time
import types
import wave
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Headless-Tkinter-Stub
try:
    import tkinter  # noqa: F401
except ModuleNotFoundError:
    class _M(types.ModuleType):
        TclError = type("TclError", (Exception,), {})
        class Tk: pass
        class Frame: pass
        class StringVar:
            def __init__(s, *a, **k): pass
            def get(s): return ""
            def set(s, v): pass
        class BooleanVar:
            def __init__(s, *a, **k): pass
            def get(s): return False
            def set(s, v): pass
        class DoubleVar:
            def __init__(s, *a, **k): pass
            def get(s): return 1.0
            def set(s, v): pass
        NONE = N = S = E = W = CENTER = LEFT = RIGHT = TOP = BOTTOM = ""
        HORIZONTAL = VERTICAL = BOTH = ALL = END = X = Y = ""
        DISABLED = NORMAL = ACTIVE = WORD = ""
        def __getattr__(s, n):
            return lambda *a, **k: None
    for _n in ("tkinter", "tkinter.ttk", "tkinter.filedialog",
               "tkinter.messagebox"):
        sys.modules[_n] = _M(_n)

import numpy as np

from app import paths  # noqa: E402
paths.ensure_directories()
from app.hardware.detector import detect_hardware  # noqa: E402
from app.pronunciation import PronunciationEngine  # noqa: E402
from app.security.identity_lock import load_production  # noqa: E402
from app.text.normalize import NormalizationReport, normalize_text  # noqa: E402
from app.tts.engine_base import SynthesisRequest  # noqa: E402
from app.jobs.runner import build_engine  # noqa: E402
from app.jobs.runner import JobSpec  # noqa: E402

OUT_DIR = paths.OUTPUT_DIR / "pron_regression"
OUT_DIR.mkdir(parents=True, exist_ok=True)

VOICES = [
    "de_male_warm_storytelling_authoritative_01",
    "de_male_warm_storytelling_authoritative_02",
]

SENTENCES = [
    "Mathematik ist die Sprache der Zahlen.",
    "Die Mathematik beschreibt Muster, Mengen und Strukturen.",
    "Ein mathematischer Algorithmus kann komplexe Probleme lösen.",
    "Quantenphysik und Mathematik bilden eine wichtige Grundlage moderner Forschung.",
]

A_VARIANTS = {
    # A/B-Vergleich für kritische Wörter: A=Original, B=optimierte
    # Respelling. Der Audit vergleicht beide Ergebnisse.
    "Mathematik": [
        ("A_original", "Mathematik"),
        ("B_respell",  "Ma-te-MA-tik"),
    ],
    "Algorithmus": [
        ("A_original", "Algorithmus"),
        ("B_respell",  "Al-go-RITH-mus"),
    ],
    "Quantenphysik": [
        ("A_original", "Quantenphysik"),
        ("B_respell",  "KUAN-ten-fy-sik"),
    ],
}


def _wav_stats(path: Path) -> dict:
    try:
        import soundfile as sf
        data, sr = sf.read(str(path))
        peak = float(np.max(np.abs(data))) if data.size else 0.0
        rms = float(np.sqrt(np.mean(data.astype(np.float64) ** 2))) if data.size else 0.0
        return {"sample_rate": sr, "samples": int(data.size),
                "channels": int(data.ndim), "peak": peak, "rms": rms,
                "duration_s": float(data.size / sr) if sr else 0.0,
                "silent": bool(peak < 0.005)}
    except Exception as e:
        # Fallback: stdlib wave
        try:
            with wave.open(str(path), "rb") as w:
                n = w.getnframes(); sr = w.getframerate()
                return {"sample_rate": sr, "samples": n,
                        "channels": w.getnchannels(), "peak": -1, "rms": -1,
                        "duration_s": float(n / sr) if sr else 0.0,
                        "silent": None,
                        "read_error": f"soundfile: {e}"}
        except Exception as e2:
            return {"error": f"{e} :: {e2}"}


def _tts_for(engine, text: str, language: str = "German") -> dict:
    req = SynthesisRequest(text=text, language=language, speed=1.0,
                           speaker=None, max_seconds_hint=30.0)
    t0 = time.perf_counter()
    res = engine.synthesize(req)
    elapsed = time.perf_counter() - t0
    return {"res": res, "elapsed_s": elapsed}


def _write_wav(path: Path, wav: np.ndarray, sr: int) -> None:
    try:
        import soundfile as sf
        sf.write(str(path), wav, sr, subtype="PCM_24")
    except Exception:
        import wave
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2)
            w.setframerate(sr)
            pcm = np.clip(wav, -1.0, 1.0)
            pcm = (pcm * 32767).astype(np.int16)
            w.writeframes(pcm.tobytes())


def main() -> int:
    hw = detect_hardware()
    if hw.mode == "cpu" and not hw.gpu_name:
        print("SKIP: Keine CUDA-GPU – Live-TTS-Regressionstest nur auf Host ausführbar.")
        print("(Offline-Audit via tools/pronunciation_audit.py ist unabhängig.)")
        return 0
    pron = PronunciationEngine()
    production = load_production()
    summary = {"voices": {}, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    for voice_id in VOICES:
        print(f"\n=== voice={voice_id} ===")
        spec = JobSpec(voice_id=voice_id, text=".", language="German",
                       speed=1.0, formats="wav", output_mode="full")
        engine, entry = build_engine(spec, production)
        try:
            engine.load()
        except Exception as e:
            print(f"SKIP load failed for {voice_id}: {e}")
            summary["voices"][voice_id] = {"load_error": str(e)}
            continue
        vdir = OUT_DIR / voice_id
        vdir.mkdir(parents=True, exist_ok=True)
        sent_reports = []
        for i, sent in enumerate(SENTENCES, 1):
            norm = normalize_text(sent, "German", NormalizationReport())
            pr = pron.process(norm, "German")
            tts_text = pr.text
            try:
                r = _tts_for(engine, tts_text)
                wav_path = vdir / f"sent_{i:02d}.wav"
                _write_wav(wav_path, r["res"].waveform, r["res"].sample_rate)
                stats = _wav_stats(wav_path)
                print(f" sent {i}: {wav_path.name}  "
                      f"{stats.get('duration_s','?'):.2f}s  "
                      f"elapsed={r['elapsed_s']:.1f}s  "
                      f"peak={stats.get('peak',-1):.3f}")
                sent_reports.append({
                    "index": i, "original": sent, "normalized": norm,
                    "tts_text": tts_text, "wav": str(wav_path),
                    "elapsed_s": r["elapsed_s"], **stats,
                    "replacements": pr.replacements,
                })
            except Exception as e:
                import traceback
                print(f" sent {i}: FAILED {e}")
                sent_reports.append({
                    "index": i, "original": sent, "normalized": norm,
                    "tts_text": tts_text, "error": str(e),
                    "traceback": traceback.format_exc()[-1500:],
                })
        # A/B-Varianten (nur Einwort-Sätze: "Mathematik." etc.)
        ab_reports = []
        for term, variants in A_VARIANTS.items():
            for label, form in variants:
                txt = form + "."
                try:
                    r = _tts_for(engine, txt)
                    wav_path = vdir / f"AB_{term}_{label}.wav"
                    _write_wav(wav_path, r["res"].waveform, r["res"].sample_rate)
                    stats = _wav_stats(wav_path)
                    print(f" AB {term} {label}: {wav_path.name} "
                          f"{stats.get('duration_s','?'):.2f}s")
                    ab_reports.append({"term": term, "variant": label,
                                       "form": form, "wav": str(wav_path),
                                       "elapsed_s": r["elapsed_s"], **stats})
                except Exception as e:
                    ab_reports.append({"term": term, "variant": label,
                                       "form": form, "error": str(e)})
        try:
            engine.unload()
        except Exception:
            pass
        summary["voices"][voice_id] = {
            "backend_mode": entry.backend_mode,
            "sentences": sent_reports,
            "ab_variants": ab_reports,
        }
    rep_path = OUT_DIR / "pron_regression_report.json"
    rep_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"\nWrote {rep_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
