#!/usr/bin/env python3
"""Long-form baseline runner.

Two supported modes, both write per-voice WAV + metrics JSON + segment table
and a combined Markdown summary under the chosen output root:

  Baseline (default, 7 selected voices) -> project/reproduction/longform/<vid>/
  Top-3 real run (--top3 or --voices top3) -> project/reproduction/TOP3_LONGFORM_REAL/<vid>/

CLI:
    --voices CSV            comma-separated voice_ids (default: the 7 selected).
                            Special token "top3" expands to the three
                            user-favourite voices (see TOP3_VOICES below).
    --top3                  Shorthand for --voices top3 --out
                            project/reproduction/TOP3_LONGFORM_REAL.
    --fresh                 Disable the *segment audio* cache for this run so
                            every segment is genuinely re-synthesised.
                            Reference WAVs / VoiceClone prompts are still
                            reused; existing baseline cache on disk is NOT
                            deleted.
    --out DIR               Override output directory.
    --allow-design          Allow VoiceDesign fallback if reference WAV/MP3 is
                            missing (default: skip that voice).

The script NEVER overwrites existing short/audition WAVs. It prefers the
Qwen VoiceDesign reference WAV in cache/voice_refs/<vid>.wav; if missing but
the registry contains an MP3 reference, VoiceCloneEngine auto-transcodes it
to 24 kHz mono WAV once.
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

# The seven voices for the main baseline. These keep running as before so
# existing 7/7 baseline results remain comparable.
DEFAULT_VOICES = [
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

# Backwards-compat alias (kept so external callers/notes referring to the old
# name keep working).
TARGET_VOICES = list(DEFAULT_VOICES)

# The user's three favourite voices for the dedicated "real" validation run.
TOP3_VOICES = [
    "de_female_warm_empathetic_01",
    "de_female_deep_warm_documentary_01",
    "en_male_warm_grounded_humanist_01",
]

# Arena voice ids – mirrors reproduce_premium.REVERSE_PRIORITY without
# importing that heavy script during summary generation.
_ARENA_ID_BY_VOICE = {
    "en_male_deep_authoritative_scholar_01":   "VOICE22_READY",
    "en_male_deep_clear_insightful_01":        "VOICE24_READY",
    "en_male_warm_grounded_humanist_01":       "VOICE25_READY",
    "en_male_extremely_natural_deep_conversational_01": "VOICE27_READY",
    "de_male_deep_natural_conversational_01":  "VOICE32_READY",
    "de_female_deep_warm_documentary_01":      "VOICE33_READY",
    "de_female_deep_calm_intelligent_01":      "VOICE34_READY",
    "de_female_warm_empathetic_01":            "VOICE40_READY",
}

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
            allow_design: bool, fresh: bool = False,
            run_tag: str | None = None) -> dict:
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

    # Stable cfg for the pipeline (single voice, no voice switching mid-run).
    # When --fresh is set we disable the *segment audio* cache only, so this
    # pipeline instance truly re-synthesises every segment. Reference WAVs /
    # VoiceClone prompts continue to be reused and the on-disk cache for other
    # runs is NOT touched or deleted.
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
            "cache_enabled": bool(not fresh),
            "segment_target_chars": 420,
            "segment_min_chars": 120,
            "segment_max_chars": 700,
            "qc_enabled": True,
            "qc_max_attempts": 3,
            "qc_min_score": 78,
            "target_lufs": -14.0,
            "true_peak_dbtp": -1.5,
            "attn_implementation": "sdpa",
            "longform_run_tag": run_tag or "",
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
    segments_reused = int(report.get("reused") or 0)
    segments_regen = int(report.get("regenerated") or 0)
    segments_failed = int(report.get("failed_segments") or 0)
    new_generation = bool(report.get("ok") and segments_reused == 0 and fresh)
    result = {
        "voice_id": voice_id,
        "arena_voice_id": _ARENA_ID_BY_VOICE.get(voice_id, "") or getattr(entry, "arena_id", ""),
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
        "segments_reused": segments_reused,
        "segments_regenerated": segments_regen,
        "segments_failed": segments_failed,
        "avg_qc_score": report.get("avg_score"),
        "duration_s": report.get("duration_s"),
        "master": report.get("master", {}),
        "fresh": bool(fresh),
        "new_generation": new_generation,
        "run_tag": run_tag or "",
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


def _write_summary(results: list[dict], out_root: Path, title: str,
                   voices: list[str], fresh: bool, run_tag: str | None) -> None:
    lines = []
    lines.append(f"# {title}\n")
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Voices: {len(voices)} ({', '.join(voices)})")
    lines.append(f"Fresh (segment cache disabled): {'YES' if fresh else 'NO (segments may be reused)'}")
    if run_tag:
        lines.append(f"Run tag: {run_tag}")
    lines.append("")
    lines.append("| Arena-ID | voice_id | Lang | Seed | Status | Words | Segs | "
                 "Dur (s) | Reused | Regen | Failed | Avg QC | NeuGen | WAV SHA256 | Issues |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        aid = r.get("arena_voice_id") or _ARENA_ID_BY_VOICE.get(r["voice_id"], "")
        status = "OK" if r.get("ok") else "FAIL"
        if r.get("new_generation"):
            new_gen = "JA"
        elif r.get("ok"):
            new_gen = "NEIN"
        else:
            new_gen = "-"
        issues = "; ".join(filter(None, r.get("warnings", [])[:3] + r.get("errors", [])[:2])) or ""
        lines.append(
            f"| {aid} | {r['voice_id']} | {r.get('language','')} | "
            f"{r.get('production_seed','')} | {status} | "
            f"{r.get('plan',{}).get('words','')} | {r.get('plan',{}).get('n_segments','')} | "
            f"{r.get('duration_s','')} | {r.get('segments_reused','')} | "
            f"{r.get('segments_regenerated','')} | {r.get('segments_failed','')} | "
            f"{r.get('avg_qc_score','')} | {new_gen} | "
            f"{(r.get('wav_sha256','')[:16]+'...') if r.get('wav_sha256') else ''} | "
            f"{issues[:80]} |"
        )
    lines.append("\n## Markers\n")
    for m in ("VOICE22_READY","VOICE23_READY","VOICE24_READY","VOICE25_READY",
              "VOICE27_READY","VOICE32_READY","VOICE33_READY","VOICE34_READY",
              "VOICE40_READY",
              "VOICE09_PROTECTED","VOICE12_PROTECTED","VOICE30_PRESERVED",
              "GOLDEN_REFERENCE_UNCHANGED","NO_GOLDEN_REFERENCE_CHANGE",
              "LONGFORM_BASELINE_READY"):
        lines.append(f"- {m}")
    (out_root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")

    # Machine-readable summary for downstream tooling.
    run_summary = {
        "title": title,
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "voices": voices,
        "n_voices_requested": len(voices),
        "n_ok": sum(1 for r in results if r.get("ok")),
        "n_fail": sum(1 for r in results if not r.get("ok")),
        "fresh": bool(fresh),
        "run_tag": run_tag or "",
        "all_new_generation": bool(
            fresh
            and all(r.get("new_generation") for r in results if r.get("ok"))
            and all(r.get("ok") for r in results)
        ),
        "out_root": str(out_root),
        "results": results,
    }
    (out_root / "run_summary.json").write_text(
        json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_voice_list(raw_voices: str | None) -> tuple[list[str], bool]:
    """Parse the --voices CSV. Accepts the magic token "top3".

    Returns (voice_list, is_top3_mode).
    """
    if not raw_voices:
        return list(DEFAULT_VOICES), False
    tokens = [t.strip() for t in raw_voices.split(",") if t.strip()]
    out: list[str] = []
    is_top3 = False
    for t in tokens:
        if t.lower() == "top3":
            out.extend(TOP3_VOICES)
            is_top3 = True
        else:
            out.append(t)
    return out, is_top3


def main() -> int:
    ap = argparse.ArgumentParser(description="Long-form baseline runner.")
    ap.add_argument("--voices", type=str, default=None,
                    help="Comma-separated voice_ids. Accepts the special "
                         "token 'top3' for the three user-favourite voices. "
                         "Default (no flag): the 7-voice baseline set.")
    ap.add_argument("--top3", action="store_true",
                    help="Shorthand: run the three user-favourite voices and "
                         "write to project/reproduction/TOP3_LONGFORM_REAL by "
                         "default. Equivalent to --voices top3.")
    ap.add_argument("--fresh", action="store_true",
                    help="Disable segment-audio caching for this run so every "
                         "segment is genuinely re-synthesised. Reference "
                         "WAVs / VoiceClone prompts still reused; existing "
                         "cache on disk is NOT deleted.")
    ap.add_argument("--allow-design", action="store_true",
                    help="Allow VoiceDesign fallback if reference WAV/MP3 is "
                         "missing. Default: skip that voice.")
    ap.add_argument("--out", type=str, default=None,
                    help="Output directory (default depends on mode: "
                         "project/reproduction/longform for baseline, "
                         "project/reproduction/TOP3_LONGFORM_REAL for --top3).")
    args = ap.parse_args()

    setup_logging()
    paths.ensure_directories()

    # Resolve voice list + defaults
    if args.top3:
        voices = list(TOP3_VOICES)
        top3_mode = True
        title = "Long-Form TOP-3 Real Run"
        default_out = _PROJECT_ROOT / "reproduction" / "TOP3_LONGFORM_REAL"
    else:
        voices, top3_mode = _resolve_voice_list(args.voices)
        title = ("Long-Form TOP-3 Real Run" if top3_mode
                 else "Long-Form Baseline – 7 Selected Voices")
        default_out = (_PROJECT_ROOT / "reproduction" / "TOP3_LONGFORM_REAL"
                       if top3_mode
                       else _PROJECT_ROOT / "reproduction" / "longform")

    out_root = Path(args.out) if args.out else default_out
    out_root.mkdir(parents=True, exist_ok=True)

    # A fresh run gets a unique tag (recorded in run_summary.json / metrics).
    run_tag: str | None = None
    if args.fresh:
        run_tag = f"longform-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
        log.info("Fresh run requested: segment cache will be disabled (tag=%s)",
                 run_tag)

    log.info("Mode: %s | voices=%d -> %s | fresh=%s",
             title, len(voices), out_root, bool(args.fresh))

    registry = VoiceRegistry()

    results = []
    for i, vid in enumerate(voices, 1):
        log.info("===== (%d/%d) %s =====", i, len(voices), vid)
        r = run_one(registry, vid, out_root,
                    allow_design=args.allow_design,
                    fresh=bool(args.fresh),
                    run_tag=run_tag)
        results.append(r)
        log.info("[%s] ok=%s dur=%ss reused=%s regen=%s failed=%s err=%s",
                 vid, r.get("ok"), r.get("duration_s"),
                 r.get("segments_reused"), r.get("segments_regenerated"),
                 r.get("segments_failed"), r.get("errors"))

    _write_summary(results, out_root, title=title, voices=voices,
                   fresh=bool(args.fresh), run_tag=run_tag)

    n_ok = sum(1 for r in results if r.get("ok"))
    n_fail = sum(1 for r in results if not r.get("ok"))
    log.info("%s complete: %d ok / %d fail -> %s",
             title, n_ok, n_fail, out_root / "SUMMARY.md")

    # Surface a non-zero exit when fresh mode failed to guarantee new segs.
    if args.fresh and n_fail == 0:
        non_fresh = [r["voice_id"] for r in results
                     if r.get("ok") and int(r.get("segments_reused") or 0) != 0]
        if non_fresh:
            log.error("Fresh run requested but segments were reused for: %s",
                      ", ".join(non_fresh))
            return 2
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
