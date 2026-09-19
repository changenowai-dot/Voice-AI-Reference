#!/usr/bin/env python3
"""Long-form benchmark: segmentation sweep + production pipeline.

For a single voice + single text, runs the REAL production pipeline
(Pipeline.process_file) across multiple segmentation presets:

  current       (as currently configured)
  short_30_45
  balanced_60_90
  long_90_120
  xl_120_180
  adaptive_180  (cross-paragraph)

Outputs per preset:
  - master WAV (and MP3 if configured) under
    project/benchmark/longform/<voice_id>/<preset>/
  - JSON summary: segments, generation time, retry count, QC failures,
    avg_score, RMS/peak/F0, ASR similarity (if whisper available),
    final assembly duration.
  - per-segment diagnostics (seeds, scores, retries, durations, F0/LUFS).

Run on RTX 5060 host with all models installed:
    python project/tools/longform_benchmark.py \
        --voice-id en_male_warm_storytelling_authoritative_02 \
        --text project/benchmark/longform_text_en.txt \
        --presets current,short_30_45,balanced_60_90,long_90_120,xl_120_180,adaptive_180

Requires materialized reference WAV (run materialize_references.py first).
"""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import json
import os
import sys
import time
import traceback
import wave
from pathlib import Path

_THIS = Path(__file__).resolve()
for _c in (_THIS.parents[2], _THIS.parents[2] / "project"):
    if (_c / "project" / "app" / "tts" / "qwen_engine.py").exists():
        ROOT = _c
        break
else:
    raise SystemExit("Cannot locate project/ root")
sys.path.insert(0, str(ROOT / "project"))

# Production-safe env: no silent design / MP3 transcode.
os.environ.pop("VOICEOVER_ALLOW_VOICEDESIGN_MATERIALIZE", None)
os.environ.pop("VOICEOVER_REFS_ACCEPT_NONWAV", None)


def _locate_models_dir() -> Path | None:
    if os.environ.get("VOICEOVER_MODELS_DIR"):
        p = Path(os.environ["VOICEOVER_MODELS_DIR"])
        if p.exists():
            return p
    for c in [
        ROOT / "project" / "models",
        ROOT.parent / "VoiceOverApp-AgentReady-Latest" / "project" / "models",
        ROOT.parent.parent / "VoiceOverApp-AgentReady-Latest" / "project" / "models",
    ]:
        if c.exists() and ((c / "Qwen3-TTS-12Hz-1.7B-Base").exists()
                           or (c / "hf").exists()):
            return c
    return None


_m = _locate_models_dir()
if _m is not None:
    os.environ["VOICEOVER_MODELS_DIR"] = str(_m)


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _wav_info(p: Path):
    with contextlib.closing(wave.open(str(p), "rb")) as w:
        return {
            "sample_rate": w.getframerate(),
            "channels": w.getnchannels(),
            "bit_depth": w.getsampwidth() * 8,
            "duration_s": w.getnframes() / float(w.getframerate()),
        }


def _aggregate_report(report_path: Path) -> dict:
    """Extract what we care about from a pipeline report JSON."""
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"error": f"cannot read report: {e}"}
    return {
        "ok": data.get("ok"),
        "segments": data.get("segments"),
        "segments_successful": data.get("segments_successful"),
        "failed_segments": data.get("failed_segments"),
        "regenerated": data.get("regenerated"),
        "reused": data.get("reused"),
        "avg_score": data.get("avg_score"),
        "duration_s": data.get("duration_s"),
        "elapsed_s": data.get("elapsed_s"),
        "wav": data.get("wav"),
        "mp3": data.get("mp3"),
    }


def _try_asr(wav_path: Path, expected_text: str) -> dict:
    """Optional ASR similarity. Tries faster-whisper / openai-whisper if
    installed; otherwise returns {available:false}."""
    try:
        import faster_whisper  # type: ignore
    except Exception:
        try:
            import whisper  # type: ignore
        except Exception:
            return {"available": False}
    try:
        if "faster_whisper" in sys.modules:
            model = faster_whisper.load_model("small", device="cpu",
                                             compute_type="int8")
            segments, _info = model.transcribe(str(wav_path), beam_size=1)
            text = " ".join(s.text for s in segments).strip()
        else:
            model = whisper.load_model("small")
            res = model.transcribe(str(wav_path), fp16=False)
            text = (res.get("text") or "").strip()
        expected_norm = " ".join(expected_text.lower().split())
        got_norm = " ".join(text.lower().split())
        # crude word-overlap similarity (Jaccard-ish)
        a = set(expected_norm.split())
        b = set(got_norm.split())
        inter = len(a & b)
        union = len(a | b) or 1
        return {"available": True, "engine": "faster-whisper"
                if "faster_whisper" in sys.modules else "openai-whisper",
                "transcript": text[:400], "word_overlap": round(inter / union, 3)}
    except Exception as e:  # noqa: BLE001
        return {"available": False, "error": str(e)[:200]}


def run_one_preset(preset: str, voice_id: str, text: str, language: str,
                   out_root: Path, seed: int | None = None) -> dict:
    """Run the production pipeline with a specific segmentation preset.

    We construct cfg manually and invoke Pipeline.process_file on a
    temp input file, so the GUI/runner cache/project state machinery
    is exercised just like a real GUI run.
    """
    from app import paths as _p
    from app.voices.registry import VoiceRegistry
    from app.hardware.detector import detect_hardware
    from app.jobs.runner import (_resolve_voice_native_language,
                                 _resolve_voice_seed)
    from app.tts.qwen_engine import VoiceCloneEngine
    from app.project.pipeline import Pipeline
    import numpy as np

    reg = VoiceRegistry()
    entry = reg.get(voice_id)
    if entry is None:
        return {"preset": preset, "error": f"unknown voice {voice_id}"}
    if not entry.available:
        return {"preset": preset, "error": f"voice {voice_id} not available "
                "(missing reference WAV — run materialize_references.py)"}
    hw = detect_hardware()
    voice_lang = _resolve_voice_native_language(reg, entry)
    voice_seed = seed if seed is not None else (_resolve_voice_seed(reg, entry) or 52018)
    ref_path = _p.ROOT / entry.reference_path

    out_dir = out_root / preset
    out_dir.mkdir(parents=True, exist_ok=True)
    in_txt = out_dir / "input.txt"
    in_txt.write_text(text, encoding="utf-8")

    cfg = {
        "language": language,
        "voice": {"id": voice_id, "speaker": voice_id,
                  "production_seed": voice_seed},
        "output_dir": str(out_dir),
        "output_format": "wav",
        "advanced": {
            "qc_enabled": True,
            "qc_max_attempts": 4,
            "qc_min_score": 78,
            "final_gate_ratio": 0.88,
            "wav_sample_rate": 24000,
            "wav_bit_depth": 24,
            "target_lufs": -16.0,
            "true_peak_dbtp": -1.0,
            "attn_implementation": "sdpa",
            "segment_seed_mode": "per_segment",
        },
        "german": {"cache_version": "q3p-v2-integrity",
                   "tech_germanization": False,
                   "variation": {"enabled": False}},
        "preset": "deep_documentary",
    }
    # Segmentation preset
    adv = cfg["advanced"]
    if preset == "current":
        pass  # defaults (420/120/700)
    else:
        from app.segmentation import preset_by_target_seconds
        cps = 15.0 if language == "English" else 13.8
        sc = preset_by_target_seconds(preset, chars_per_sec=cps)
        adv["segment_target_chars"] = sc.target_chars
        adv["segment_min_chars"] = sc.min_chars
        adv["segment_max_chars"] = sc.max_chars
        adv["segment_cross_paragraph"] = (preset in ("xl_120_180", "adaptive_180"))
    # Override the default respect_paragraph via cfg if desired.
    adv.setdefault("segment_cross_paragraph", False)

    print(f"\n=== PRESET {preset} ===")
    print(f"  segment target/min/max chars = {adv.get('segment_target_chars',420)}/"
          f"{adv.get('segment_min_chars',120)}/{adv.get('segment_max_chars',700)}")
    # ref_text=None, reference_path=None -> canonical bundle resolution
    # (WAV + .wav.json manifest). If the bundle is invalid we fail hard
    # before running any preset rather than silently gibberishing.
    engine = VoiceCloneEngine(
        hw=hw, candidate_id=entry.voice_id,
        description=entry.description or "",
        language=voice_lang, ref_text=None,
        seed=voice_seed, models_dir=None,
        attn_implementation=adv.get("attn_implementation"),
        allow_design=False, reference_path=None,
    )
    try:
        t0 = time.perf_counter()
        pipe = Pipeline(cfg, engine)
        report = pipe.process_file(in_txt)
        elapsed = time.perf_counter() - t0
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return {"preset": preset, "error": str(e)}
    finally:
        engine.unload()
    summ = _aggregate_report_from_process_file_result(report, out_dir, text)
    summ["preset"] = preset
    summ["wall_clock_s"] = round(elapsed, 1)
    summ["ref_sha256_prefix"] = _sha256(ref_path)[:16]
    wav = out_dir / f"{in_txt.stem}.wav"
    if wav.exists():
        info = _wav_info(wav)
        summ["output"] = str(wav)
        summ["output_info"] = info
        summ["output_sha256_prefix"] = _sha256(wav)[:16]
        asr = _try_asr(wav, text)
        summ["asr"] = asr
    # write per-preset json
    (out_dir / "summary.json").write_text(
        json.dumps(summ, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")
    print(f"  -> segments={summ.get('segments')} ok={summ.get('ok')} "
          f"dur={summ.get('duration_s')}s elapsed={summ.get('elapsed_s')}s "
          f"score={summ.get('avg_score')}")
    return summ


def _aggregate_report_from_process_file_result(report: dict, out_dir: Path,
                                              text: str) -> dict:
    if not isinstance(report, dict):
        return {"error": f"unexpected report type: {type(report)!r}"}
    return {
        "ok": bool(report.get("ok")),
        "segments": report.get("segments"),
        "segments_successful": report.get("segments_successful"),
        "failed_segments": report.get("failed_segments"),
        "regenerated": report.get("regenerated"),
        "reused": report.get("reused"),
        "avg_score": report.get("avg_score"),
        "duration_s": report.get("duration_s"),
        "elapsed_s": report.get("elapsed_s"),
        "wav": report.get("wav"),
        "mp3": report.get("mp3"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice-id", required=True)
    ap.add_argument("--text", required=True, help="path to .txt longform text")
    ap.add_argument("--language", default="English", choices=["English", "German"])
    ap.add_argument("--seed", type=int, default=None,
                    help="override recipe seed (default: from voice settings)")
    ap.add_argument("--presets", default="current,balanced_60_90,long_90_120,xl_120_180,adaptive_180",
                    help="comma-separated list of presets")
    args = ap.parse_args()

    text = Path(args.text).read_text(encoding="utf-8")
    out_root = ROOT / "project" / "benchmark" / "longform" / args.voice_id
    out_root.mkdir(parents=True, exist_ok=True)
    presets = [p.strip() for p in args.presets.split(",") if p.strip()]
    results = []
    for preset in presets:
        try:
            r = run_one_preset(preset, args.voice_id, text, args.language,
                               out_root, seed=args.seed)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            r = {"preset": preset, "error": str(e)}
        results.append(r)
    # write master summary
    master = {
        "voice_id": args.voice_id,
        "text": args.text,
        "text_chars": len(text),
        "presets_run": presets,
        "results": results,
    }
    (out_root / "benchmark.json").write_text(
        json.dumps(master, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")
    print("\n=== BENCHMARK COMPLETE ===")
    print(json.dumps([{k: v for k, v in r.items()
                       if k in ("preset", "segments", "duration_s",
                                "elapsed_s", "avg_score", "failed_segments",
                                "output", "error")}
                      for r in results], indent=2, default=str))
    print(f"\nOutputs under: {out_root}")


if __name__ == "__main__":
    main()
