#!/usr/bin/env python3
"""Isolierter GPU-Repro-Test für ein einzelnes Segment.

Zweck (forensisch):
  Dieselbe Voice, derselbe Text, dieselben Sampling-Parameter werden
  nacheinander mit unterschiedlichen Seeds (Attempt-1, Attempt-2,
  Attempt-3 wie im echten Retry) direkt über VoiceCloneEngine
  ausgeführt. Wir rufen KEINE QC-Logik auf, damit wir sehen, ob die
  Probleme in der Generierung selbst oder in QC/Pipeline entstehen.

Ausgabe: pro Attempt seed, gen_kwargs, Sample-Anzahl, Dauer, RMS,
geschätztes F0/LUFS sowie SHA256 der WAV. Wenn zwei aufeinander-
folgende Versuche mit unterschiedlichem Seed bit-identisch oder wieder
0.16s / silence liefern, ist das ein Modell-/RNG-/Conditioning-Bug.

Aufruf auf dem RTX-5060-Host aus dem Projekt-Root:
    .venv\\Scripts\\python.exe tools\\repro_segment_retry.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

_PROJECT = Path(__file__).resolve().parents[1]
_REPO = _PROJECT.parent
for p in (str(_PROJECT), str(_REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from app import config as cfgmod, paths  # noqa: E402
from app.hardware.detector import detect_hardware  # noqa: E402
from app.logging_setup import setup_logging, get_logger  # noqa: E402
from app.tts.engine_base import SynthesisRequest  # noqa: E402
from app.tts.qwen_engine import VoiceCloneEngine  # noqa: E402
from app.tts.sampler import max_new_tokens_for, params_for_set  # noqa: E402

log = get_logger("repro")


def _rms(x) -> float:
    import numpy as np
    return float(np.sqrt(float((x.astype("float64") ** 2).mean())))


def _lufs_approx(x, sr: int) -> float:
    # Sehr grobe Annäherung (RMS -> LUFS) ohne ffmpeg/ebu_r128:
    # nur für Diagnose; -70 wird als "still" erkannt.
    import numpy as np
    r = _rms(x)
    if r <= 0:
        return -120.0
    return float(20 * __import__("math").log10(max(r, 1e-12)) - 0.691)


def _f0_estimate(x, sr: int) -> float:
    try:
        import numpy as np
        x = x - float(np.mean(x))
        if _rms(x) < 0.003:
            return 0.0
        # Einfache Autokorrelation im Sprachbereich 70..400 Hz
        min_lag = int(sr / 400)
        max_lag = int(sr / 70)
        if len(x) < max_lag + 1:
            return 0.0
        corr = np.correlate(x, x, mode="full")[len(x)-1:]
        seg = corr[min_lag:max_lag]
        if seg.size == 0:
            return 0.0
        lag = int(seg.argmax()) + min_lag
        val = float(corr[lag]) / (float(corr[0]) + 1e-9)
        if val < 0.3:
            return 0.0
        return float(sr / lag)
    except Exception:
        return -1.0


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16].upper()


def run(voice_id: str, text: str, language: str, out_dir: Path,
        seed: int, attempts: list[tuple[int, dict, str]]):
    paths.ensure_directories()
    out_dir.mkdir(parents=True, exist_ok=True)
    setup_logging()
    hw = detect_hardware()
    from app.voices.registry import VoiceRegistry
    from app.jobs.runner import (_resolve_voice_native_language,
                                  _resolve_voice_seed)
    registry = VoiceRegistry()
    entry = registry.get(voice_id)
    if entry is None:
        raise SystemExit(f"Stimme {voice_id} nicht in Registry")
    native_lang = language or _resolve_voice_native_language(registry, entry)
    vseed = seed if seed != -1 else _resolve_voice_seed(registry, entry)

    eng = VoiceCloneEngine(hw=hw, candidate_id=voice_id,
                           description=entry.description or voice_id,
                           language=native_lang, seed=vseed)
    eng.load()

    sampling = params_for_set("balanced")
    results = []
    base_seed = int(vseed or 12345) & 0xFFFFFFFF
    # Versuch-Aufbau, wie in generate_with_qc:
    #   attempt 1: base_seed                (Balanced)
    #   attempt 2: base_seed + 10009        (gem. Fehlerklasse Sampling)
    #   attempt 3: base_seed + 100003       (gem. Fehlerklasse Sampling)
    import numpy as np
    all_cases = [
        (1, base_seed,            dict(sampling), "balanced/base"),
        (2, base_seed + 10009,    {**sampling, "temperature": 0.55,
                                   "top_p": 0.85, "top_k": 40,
                                   "repetition_penalty": 1.08}, "retry-pron"),
        (3, base_seed + 100003,   {**sampling, "temperature": 0.55,
                                   "top_p": 0.85, "top_k": 40,
                                   "repetition_penalty": 1.10}, "retry-cons"),
        # Unabhängiger direkter Kontrollaufruf mit neuem Seed:
        (4, base_seed + 200003,   dict(sampling), "independent-new-seed"),
    ]
    for i, attn, att_seed, samp, label in all_cases:
        # Je Versuch einen kleinen max_new_tokens-Hint basierend auf Textlänge
        max_s = max(4.0, len(text) / (13.8 if native_lang.lower().startswith("ger") else 15.0))
        req = SynthesisRequest(text=text, language=native_lang,
                               speaker=voice_id, instruct="",
                               sampling=samp, seed=int(att_seed),
                               max_seconds_hint=max_s, speed=1.0)
        t0 = time.perf_counter()
        try:
            res = eng.synthesize(req)
        except Exception as e:
            results.append({"attempt": attn, "label": label, "seed": att_seed,
                            "error": str(e)})
            log.error("Attempt %d fehlgeschlagen: %s", attn, e)
            continue
        dt = time.perf_counter() - t0
        wav = np.asarray(res.waveform, dtype=np.float32)
        dur = float(len(wav) / res.sample_rate)
        rms = _rms(wav)
        lufs = _lufs_approx(wav, res.sample_rate)
        f0 = _f0_estimate(wav, res.sample_rate)
        sha = _sha(wav.tobytes())
        out_wav = out_dir / f"attempt_{attn}_{label}_s{att_seed}.wav"
        try:
            from app.audio.io import write_wav
            write_wav(out_wav, wav, res.sample_rate, bit_depth=16)
        except Exception as e:
            log.warning("WAV-Schreiben fehlgeschlagen: %s", e)
        rec = {
            "attempt": attn, "label": label, "seed": att_seed,
            "sampling": samp, "samples": int(len(wav)), "duration_s": round(dur, 3),
            "rms": round(rms, 5), "lufs_approx": round(lufs, 2),
            "f0_hz": round(f0, 1), "wav_sha256_16": sha,
            "wav_path": str(out_wav), "elapsed_s": round(dt, 2),
            "params_used": res.params_used,
        }
        results.append(rec)
        log.warning(
            "REPRO attempt=%d label=%s seed=%d dur=%.3fs rms=%.5f "
            "lufs≈%.1f f0≈%.1fHz sha=%s",
            attn, label, att_seed, dur, rms, lufs, f0, sha)

    eng.unload()
    (out_dir / "repro_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    # Diagnose: Gibt es zwei identische SHA?
    shas = [r.get("wav_sha256_16") for r in results]
    if len(set(shas)) != len(shas):
        log.warning("ACHTUNG: Mindestens zwei Versuche erzeugten IDENTISCHE WAV-Daten!")
    else:
        log.info("Alle Versuche erzeugten unterschiedliche WAV-Daten ✅")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="de_female_warm_empathetic_01")
    ap.add_argument("--text", default=(
        "Die Industrialisierung hat die Lebensverhältnisse in Europa "
        "nachhaltig verändert. Fabriken entstanden, Städte wuchsen, und "
        "viele Menschen zogen vom Land in die Ballungsgebiete."))
    ap.add_argument("--language", default="German")
    ap.add_argument("--seed", type=int, default=-1,
                    help="Force segment seed; -1 = nutze Voice-Production-Seed")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out_dir = Path(args.out) if args.out else _PROJECT / "reproduction" / "SEED_REPRO"
    run(args.voice, args.text, args.language, out_dir, args.seed, attempts=[])


if __name__ == "__main__":
    main()
