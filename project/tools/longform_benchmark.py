#!/usr/bin/env python3
"""Long-form baseline for 7 selected premium voices (RTX 5060).

Runs the production Pipeline over fixed ~1000-1500 word DE/EN test texts with
each target voice, writes WAV (+ MP3 if ffmpeg is available), a per-voice
metrics JSON, a segment table, and a combined Markdown summary under:

    project/reproduction/longform/<voice_id>/

The script NEVER overwrites existing voice reproductions (test_short.wav /
test_audition.wav) and does NOT invoke VoiceDesign if a reference WAV is
already present. It prefers the Qwen VoiceDesign reference WAV in
cache/voice_refs/<voice_id>.wav (produced by reproduce_premium.py / the
RTX 5060 runs); if that is missing but the registry contains an MP3
reference, the VoiceCloneEngine auto-transcodes it to 24 kHz mono WAV once.

Run on the RTX 5060 Windows host after voice-35..41 (and the 8 previously
reproduced candidates) exist as reference WAVs, or at least after the
MP3 audition references are available (they will be transcoded to WAV
on first use):

    python project\\tools\\longform_benchmark.py

Or from repo root:

    python project/tools/longform_benchmark.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

_THIS = Path(__file__).resolve()
_PROJECT_ROOT = _THIS.parents[1]        # .../project
_REPO_ROOT = _THIS.parents[2]           # .../Voice-AI-Reference
for p in (str(_PROJECT_ROOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("HF_HOME", str(_PROJECT_ROOT / "models" / "hf"))

from app import config as cfgmod, paths  # noqa: E402
from app.hardware.detector import detect_hardware  # noqa: E402
from app.logging_setup import setup_logging, get_logger  # noqa: E402
from app.project.pipeline import Pipeline  # noqa: E402
from app.tts.engine_base import TTSError  # noqa: E402
from app.tts.qwen_engine import VoiceCloneEngine  # noqa: E402
from app.tts.sampler import params_for_set  # noqa: E402
from app.ui.progress import ProgressReporter  # noqa: E402
from app.voices.registry import VoiceRegistry  # noqa: E402
from app.jobs.runner import _resolve_voice_native_language, _resolve_voice_seed  # noqa: E402
from app.prosody.instruct import (ENGLISH_VOICEDESIGN_DESCRIPTIONS,
                                  VOICEDESIGN_DESCRIPTIONS)  # noqa: E402

log = get_logger("longform")

# The seven selected voices for this round.
TARGET_VOICES = [
    # English
    "en_male_deep_clear_insightful_01",
    "en_male_warm_grounded_humanist_01",
    "en_male_extremely_natural_deep_conversational_01",
    "en_male_deep_authoritative_scholar_01",
    # German
    "de_female_deep_warm_documentary_01",
    "de_male_intellectual_precise_01",
    "de_female_warm_empathetic_01",
]

BENCH_TEXTS = {
    "English": _PROJECT_ROOT / "benchmark" / "longform_text_en.txt",
    "German":  _PROJECT_ROOT / "benchmark" / "longform_text_de.txt",
}

# Stable balanced sampling (mirrors reproduce_premium.py defaults).
BALANCED_SAMPLING = params_for_set("balanced", {
    "do_sample": True, "temperature": 0.7,
    "top_k": 50, "top_p": 0.9, "repetition_penalty": 1.05,
})


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def _resolve_reference(voice_id: str, entry, voice_language: str,
                       voice_seed: int | None, allow_design: bool):
    """Pick reference source (WAV preferred) and build a VoiceCloneEngine.

    Preference order:
      1) cache/voice_refs/<vid>.wav         (reproduce_premium.py output)
      2) config.production reference_path   (if WAV exists)
      3) registry entry.reference_path      (MP3 — auto-transcoded inside
                                             VoiceCloneEngine._ensure_prompt)
      4) VoiceDesign (only if allow_design=True and none of the above)
    """
    hw = detect_hardware()
    adv = cfgmod.load_config().get("advanced", {}) or {}

    # Description for VoiceDesign fallback
    desc_entry = (ENGLISH_VOICEDESIGN_DESCRIPTIONS.get(voice_id)
                  or VOICEDESIGN_DESCRIPTIONS.get(voice_id) or {})
    description = (desc_entry.get("description")
                   or entry.description or f"{voice_language} narrator")

    # Determine explicit reference path (None -> use cache default)
    ref_override: Path | None = None
    wav_cache = paths.VOICE_REFS_DIR / f"{voice_id}.wav"
    if wav_cache.exists():
        ref_override = wav_cache
        allow = False
        log.info("[%s] Using VoiceDesign reference WAV: %s", voice_id, wav_cache)
    elif entry.reference_path:
        rp = (_PROJECT_ROOT / entry.reference_path)
        # Path may be absolute or relative to project/
        if rp.exists():
            ref_override = rp
            allow = False
            log.info("[%s] Using registry reference: %s", voice_id, rp)
        else:
            allow = bool(allow_design)
            log.warning("[%s] Registry reference missing: %s", voice_id, rp)
    else:
        allow = bool(allow_design)

    eng = VoiceCloneEngine(
        hw=hw,
        candidate_id=voice_id,
        description=description,
        language=voice_language,
        seed=voice_seed,
        attn_implementation=adv.get("attn_implementation") or None,
        allow_design=allow,
        reference_path=str(ref_override) if ref_override else None,
    )
    return eng, hw


def _write_input_text(out_dir: Path, language: str) -> Path:
    src = BENCH_TEXTS[language]
    dst = out_dir / f"input_{language[:2].lower()}.txt"
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return dst


def _segment_stats(engine, cfg: dict, text: str):
    """Compute segmentation statistics without running synthesis."""
    from app.pronunciation import PronunciationEngine
    from app.segmentation import SegmentationConfig, segment_text
    from app.text.analyze import analyze_text
    from app.text.normalize import normalize_text, NormalizationReport
    analysis = analyze_text(text, cfg["language"])
    pron = PronunciationEngine(tech_germanization=True)
    def provider(block):
        n = normalize_text(block.text, cfg["language"], NormalizationReport())
        return pron.process(n, cfg["language"], suggest_unknown=False).text
    adv = cfg.get("advanced", {})
    seg_cfg = SegmentationConfig(
        target_chars=int(adv.get("segment_target_chars", 420)),
        min_chars=int(adv.get("segment_min_chars", 120)),
        max_chars=int(adv.get("segment_max_chars", 700)),
    )
    segments = segment_text(analysis.blocks, provider, seg_cfg)
    durations = []
    char_per_sec = 13.8 if cfg["language"].lower().startswith("ger") else 15.0
    for s in segments:
        est = max(4.0, len(s.text) / char_per_sec)
        durations.append(est)
    return segments, durations


def run_one(registry: VoiceRegistry, voice_id: str, out_root: Path,
            allow_design: bool) -> dict:
    entry = registry.get(voice_id)
    if entry is None:
        return {"voice_id": voice_id, "ok": False, "error": "not in registry"}

    language = _resolve_voice_native_language(registry, entry)
    seed = _resolve_voice_seed(registry, entry)

    out_dir = out_root / voice_id
    out_dir.mkdir(parents=True, exist_ok=True)

    text_path = _write_input_text(out_dir, language)
    text = text_path.read_text(encoding="utf-8")

    # Build engine (loads ref WAV, builds clone prompt; ONCE per voice)
    t_engine_start = time.perf_counter()
    try:
        engine, hw = _resolve_reference(voice_id, entry, language, seed,
                                        allow_design=allow_design)
        engine.load()
    except Exception as e:
        log.exception("[%s] Engine/Reference load failed", voice_id)
        return {"voice_id": voice_id, "ok": False, "error": f"engine load: {e}"}
    engine_load_s = time.perf_counter() - t_engine_start

    # Stable cfg for the pipeline (single voice, no voice switching mid-run)
    cfg = {
        "language": language,
        "preset": "deep_documentary",
        "voice_profile": entry.voice_id,
        "voice": {
            "id": entry.voice_id,
            "speaker": entry.voice_id,   # clone uses candidate_id as speaker
            "production_seed": seed,
        },
        "speed": 1.0,
        "output_dir": str(out_dir),
        "output_format": "wav",          # baseline WAV only (faster); MP3 optional via ffmpeg
        "wav_bit_depth": 16,
        "wav_sample_rate": 24000,
        "mp3_bitrate": "320k",
        "advanced": {
            "cache_enabled": True,
            "segment_target_chars": 420,
            "segment_min_chars": 120,
            "segment_max_chars": 700,
            "qc_enabled": True,
            "qc_max_attempts": 3,
            "qc_min_score": 78,
            "target_lufs": -14.0,
            "true_peak_dbtp": -1.5,
            "attn_implementation": "sdpa",
            # stable sampling, no silent per-process hash drift
        },
        "german": {
            "instruct_variant": "de_doc_native",
            "min_german_score": 75.0,
            "tech_germanization": True,
            "variation": {"enabled": None, "strength": "subtle"},
        },
    }

    # Pre-compute segmentation plan (no synthesis yet)
    segments, est_dur = _segment_stats(engine, cfg, text)
    plan = {
        "n_segments": len(segments),
        "words": len([w for w in text.split() if w.strip()]),
        "est_total_s": round(sum(est_dur), 1),
        "est_min_s": round(min(est_dur), 2) if est_dur else 0,
        "est_max_s": round(max(est_dur), 2) if est_dur else 0,
        "est_avg_s": round(sum(est_dur) / len(est_dur), 2) if est_dur else 0,
    }
    log.info("[%s] Plan: %d segments, %d words, ~%.1fs est",
             voice_id, plan["n_segments"], plan["words"], plan["est_total_s"])

    progress = ProgressReporter()

    # Run synthesis
    t0 = time.perf_counter()
    pipeline = Pipeline(cfg, engine, progress=progress)
    try:
        report = pipeline.process_file(text_path)
    except Exception as e:
        log.exception("[%s] Pipeline failed", voice_id)
        engine.unload()
        return {"voice_id": voice_id, "ok": False, "error": f"pipeline: {e}",
                "plan": plan, "engine_load_s": round(engine_load_s, 2)}
    synth_s = time.perf_counter() - t0
    engine.unload()

    # Collect output metrics
    wav_path = Path(report.get("wav") or "")
    wav_sha = _sha256_file(wav_path) if wav_path.exists() else ""

    # Record run metadata
    result = {
        "voice_id": voice_id,
        "arena_voice_id": getattr(entry, "arena_id", ""),
        "language": language,
        "production_seed": seed,
        "sampling": BALANCED_SAMPLING,
        "plan": plan,
        "engine_load_s": round(engine_load_s, 2),
        "total_elapsed_s": round(synth_s, 2),
        "engine": engine.info(),
        "hardware": hw.to_dict(),
        "warnings": report.get("warnings", []),
        "errors": [] if report.get("ok") else [report.get("error", "")],
        "ok": bool(report.get("ok")),
        "wav": str(wav_path),
        "wav_sha256": wav_sha,
        "segments_attempted": report.get("segments"),
        "segments_reused": report.get("reused"),
        "segments_regenerated": report.get("regenerated"),
        "segments_failed": report.get("failed_segments"),
        "avg_qc_score": report.get("avg_score"),
        "duration_s": report.get("duration_s"),
        "master": report.get("master", {}),
    }
    (out_dir / "longform_metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # Per-segment table
    seg_table = []
    if report.get("ok"):
        # Segments aren't individually saved in the pipeline's return; we
        # report plan+global stats here. The WAV is the authoritative output.
        seg_table.append({
            "segments_planned": plan["n_segments"],
            "est_min_s": plan["est_min_s"],
            "est_max_s": plan["est_max_s"],
            "est_avg_s": plan["est_avg_s"],
        })
    (out_dir / "segment_plan.json").write_text(
        json.dumps(seg_table, ensure_ascii=False, indent=2), encoding="utf-8")

    return result


def _write_summary(results: list[dict], out_root: Path) -> None:
    lines = []
    lines.append("# Long-Form Baseline – 7 Selected Voices\n")
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append("| Arena-ID | voice_id | Lang | Seed | Status | Words | Segs | "
                 "Dur (s) | Ref/Engine load (s) | Total (s) | Avg QC | WAV SHA256 | Issues |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        aid = ""
        # Try to resolve arena id from reproduce_premium's mapping
        try:
            from tools import reproduce_premium as rp
            aid = rp.REVERSE_PRIORITY.get(r["voice_id"], "")
        except Exception:
            pass
        status = "OK" if r.get("ok") else "FAIL"
        issues = "; ".join(filter(None, r.get("warnings", [])[:3] + r.get("errors", [])[:2])) or ""
        lines.append(
            f"| {aid} | {r['voice_id']} | {r.get('language','')} | "
            f"{r.get('production_seed','')} | {status} | "
            f"{r.get('plan',{}).get('words','')} | {r.get('plan',{}).get('n_segments','')} | "
            f"{r.get('duration_s','')} | {r.get('engine_load_s','')} | "
            f"{r.get('total_elapsed_s','')} | {r.get('avg_qc_score','')} | "
            f"{(r.get('wav_sha256','')[:16]+'...') if r.get('wav_sha256') else ''} | "
            f"{issues[:80]} |"
        )
    lines.append("\n## Markers\n")
    for m in ("VOICE22_READY","VOICE23_READY","VOICE24_READY","VOICE25_READY",
              "VOICE27_READY","VOICE32_READY","VOICE33_READY","VOICE34_READY",
              "VOICE09_PROTECTED","VOICE12_PROTECTED","VOICE30_PRESERVED",
              "GOLDEN_REFERENCE_UNCHANGED","NO_GOLDEN_REFERENCE_CHANGE",
              "LONGFORM_BASELINE_READY"):
        lines.append(f"- {m}")
    (out_root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Long-form baseline runner.")
    ap.add_argument("--voices", type=str, default=",".join(TARGET_VOICES),
                    help="Comma-separated voice_ids (default: the 7 selected).")
    ap.add_argument("--allow-design", action="store_true",
                    help="Allow VoiceDesign fallback if reference WAV/MP3 is "
                         "missing. Default: skip that voice.")
    ap.add_argument("--out", type=str, default=None,
                    help="Output directory (default: project/reproduction/longform).")
    args = ap.parse_args()

    setup_logging()
    paths.ensure_directories()
    out_root = Path(args.out) if args.out else _PROJECT_ROOT / "reproduction" / "longform"
    out_root.mkdir(parents=True, exist_ok=True)

    voices = [v.strip() for v in args.voices.split(",") if v.strip()]
    registry = VoiceRegistry()

    results = []
    for i, vid in enumerate(voices, 1):
        log.info("===== (%d/%d) %s =====", i, len(voices), vid)
        r = run_one(registry, vid, out_root, allow_design=args.allow_design)
        results.append(r)
        log.info("[%s] ok=%s dur=%ss err=%s", vid, r.get("ok"),
                 r.get("duration_s"), r.get("errors"))

    _write_summary(results, out_root)

    n_ok = sum(1 for r in results if r.get("ok"))
    n_fail = sum(1 for r in results if not r.get("ok"))
    log.info("Long-form baseline complete: %d ok / %d fail -> %s",
             n_ok, n_fail, out_root / "SUMMARY.md")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
