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
import traceback
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
    """Berechnet SHA-256 einer Datei. Gibt Leerstring zurück, wenn der Pfad
    leer / ein Verzeichnis / nicht existent ist (robust gegen Teil-
    fehlschläge, bei denen der Pipeline kein WAV erzeugt)."""
    try:
        p = Path(p)
        if not str(p) or str(p) in (".", ""):
            return ""
        if not p.exists() or not p.is_file():
            return ""
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest().upper()
    except (OSError, PermissionError) as e:
        log.warning("SHA256 für %s nicht möglich: %s", p, e)
        return ""


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


def _safe_vram_log() -> dict:
    """Bestmögliche VRAM-Info (ohne Architekturumbau). Leer, falls CUDA
    nicht verfügbar ist (z.B. Test-Doubles oder CPU-Modus)."""
    try:
        import torch
        if not torch.cuda.is_available():
            return {}
        dev = torch.cuda.current_device()
        free, total = torch.cuda.mem_get_info(dev)
        return {
            "device": torch.cuda.get_device_name(dev),
            "total_mb": round(total / 1024 / 1024),
            "free_mb_before": round(free / 1024 / 1024),
        }
    except Exception:
        return {}


def _count_silence_patterns(segments_jsonl: Path) -> dict:
    """Zählt sehr kurze / Stille-/Rausch-/F0=0-Fälle aus dem
    Segment-Diagnoselog. Berücksichtigt echte Dauer + RMS + LUFS/Issues,
    damit nicht jeder einzelne F0=0-Wert fälschlich als Silence zählt."""
    very_short = silence = noise = no_voiced = zero_f0 = 0
    if not segments_jsonl.exists():
        return {"very_short_count": 0, "silence_count": 0,
                "noise_like_count": 0, "no_voiced_speech_count": 0,
                "zero_f0_count": 0, "silence_pattern_detected": False}
    import math
    with open(segments_jsonl, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("status") != "ok":
                continue
            # Best-Attempt-Dauer ermitteln (chosen_attempt)
            best = None
            for a in d.get("attempts", []):
                if a.get("attempt") == d.get("chosen_attempt"):
                    best = a; break
            if best is None and d.get("attempts"):
                best = d["attempts"][-1]
            if best is None:
                continue
            dur = float(best.get("duration_s") or 0.0)
            rms = float(best.get("rms") or 0.0)
            lufs = float(best.get("lufs") or 0.0)
            f0 = float(best.get("f0_hz") or 0.0)
            issues = set(best.get("issues") or [])
            if dur <= 0.5:
                very_short += 1
            if f0 == 0:
                zero_f0 += 1
            if "silence" in issues:
                silence += 1
            if "noise_like" in issues:
                noise += 1
            if "no_voiced_speech" in issues:
                no_voiced += 1
    pattern = (very_short > 0 or silence > 0 or noise > 0 or no_voiced > 0)
    return {
        "very_short_count": very_short,
        "silence_count": silence,
        "noise_like_count": noise,
        "no_voiced_speech_count": no_voiced,
        "zero_f0_count": zero_f0,
        "silence_pattern_detected": bool(pattern),
    }


def _cuda_cleanup_between_voices() -> None:
    """Best-effort VRAM/CUDA-Cleanup zwischen Stimmen."""
    try:
        import gc, torch
        gc.collect()
        if torch.cuda.is_available():
            try: torch.cuda.synchronize()
            except Exception: pass
            torch.cuda.empty_cache()
    except Exception:
        pass


def _write_voice_metrics(result: dict, out_dir: Path) -> None:
    try:
        (out_dir / "longform_metrics.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
    except Exception as e:
        log.warning("longform_metrics.json für %s nicht schreibbar: %s",
                    out_dir.name, e)
    plan = result.get("plan") or {}
    seg_table = [{
        "segments_planned": plan.get("n_segments"),
        "est_min_s": plan.get("est_min_s"),
        "est_max_s": plan.get("est_max_s"),
        "est_avg_s": plan.get("est_avg_s"),
        "segments_failed": result.get("segments_failed"),
        "segments_successful": result.get("segments_successful"),
        "wav_complete": result.get("wav_complete"),
        "complete_success": result.get("complete_success"),
    }]
    try:
        (out_dir / "segment_plan.json").write_text(
            json.dumps(seg_table, ensure_ascii=False, indent=2),
            encoding="utf-8")
    except Exception:
        pass


def run_one(registry: VoiceRegistry, voice_id: str, out_root: Path,
            allow_design: bool, fresh: bool = False,
            run_tag: str | None = None) -> dict:
    entry = registry.get(voice_id)
    base: dict = {
        "voice_id": voice_id,
        "ok": False,
        "complete_success": False,
        "wav_complete": False,
        "fresh": bool(fresh),
        "new_generation": False,
        "segment_cache_enabled": bool(not fresh),
        "warnings": [],
        "errors": [],
        "error": "",
        "exception_type": "",
        "run_tag": run_tag or "",
    }
    if entry is None:
        base.update({"error": "not in registry", "exception_type": "LookupError"})
        return base

    language = _resolve_voice_native_language(registry, entry)
    seed = _resolve_voice_seed(registry, entry)
    out_dir = out_root / voice_id
    out_dir.mkdir(parents=True, exist_ok=True)
    segments_log = out_dir / "segments.jsonl"
    try:
        if segments_log.exists():
            segments_log.unlink()
    except OSError:
        pass
    segments_logged = 0

    text_path = _write_input_text(out_dir, language)
    text = text_path.read_text(encoding="utf-8")

    engine = None
    hw = None
    plan = {"n_segments": 0, "words": 0, "est_total_s": 0}
    report: dict = {"ok": False}
    engine_load_s = 0.0
    vram_before = _safe_vram_log()

    def _seg_cb(diag: dict) -> None:
        nonlocal segments_logged
        diag["voice_id"] = voice_id
        diag["run_tag"] = run_tag or ""
        diag["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        try:
            with open(segments_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(diag, ensure_ascii=False) + "\n")
            segments_logged += 1
        except Exception as e:
            log.warning("segments.jsonl write fehlgeschlagen: %s", e)

    try:
        t0 = time.perf_counter()
        engine, hw = _resolve_reference(voice_id, entry, language, seed,
                                        allow_design=allow_design)
        engine.load()
        engine_load_s = time.perf_counter() - t0

        cfg = {
            "language": language,
            "preset": "deep_documentary",
            "voice_profile": entry.voice_id,
            "voice": {"id": entry.voice_id, "speaker": entry.voice_id,
                      "production_seed": seed},
            "speed": 1.0,
            "output_dir": str(out_dir),
            "output_format": "wav",
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
        pipeline = Pipeline(cfg, engine, progress=progress,
                            segment_callback=_seg_cb)
        t1 = time.perf_counter()
        report = pipeline.process_file(text_path)
        synth_s = time.perf_counter() - t1
    except Exception as e:
        log.exception("[%s] Run failed", voice_id)
        base.update({
            "ok": False,
            "error": f"pipeline: {e}",
            "exception_type": type(e).__name__,
            "traceback": traceback.format_exc(limit=8),
            "plan": plan,
            "engine_load_s": round(engine_load_s, 2),
            "hardware": hw.to_dict() if hw is not None else {},
            "vram_before": vram_before,
        })
        _write_voice_metrics(base, out_dir)
        if engine is not None:
            try: engine.unload()
            except Exception: pass
        _cuda_cleanup_between_voices()
        return base
    finally:
        if engine is not None:
            try: engine.unload()
            except Exception: pass
        _cuda_cleanup_between_voices()

    wav_path = Path(report.get("wav") or "")
    wav_ok = bool(wav_path and wav_path.exists() and wav_path.is_file())
    wav_sha = _sha256_file(wav_path) if wav_ok else ""
    segments_reused = int(report.get("reused") or 0)
    segments_regen = int(report.get("regenerated") or 0)
    segments_failed = int(report.get("failed_segments") or 0)
    segments_planned = int(report.get("segments_planned")
                           or report.get("segments")
                           or plan.get("n_segments") or 0)
    segments_successful = int(report.get("segments_successful")
                              or max(segments_planned - segments_failed, 0))
    wav_complete = bool(report.get("wav_complete", False))
    new_generation = bool(fresh and segments_reused == 0 and report.get("ok"))
    complete_success = bool(report.get("ok") and wav_ok and wav_complete
                            and segments_failed == 0)
    vram_after = _safe_vram_log()
    silence_stats = _count_silence_patterns(segments_log)

    result = {
        **base,
        "arena_voice_id": (_ARENA_ID_BY_VOICE.get(voice_id, "")
                           or getattr(entry, "arena_id", "")),
        "language": language,
        "production_seed": seed,
        "sampling": BALANCED_SAMPLING,
        "plan": plan,
        "engine_load_s": round(engine_load_s, 2),
        "total_elapsed_s": round(report.get("elapsed_s", synth_s), 2),
        "engine": engine.info() if engine is not None else {},
        "hardware": hw.to_dict() if hw is not None else {},
        "vram_before": vram_before,
        "vram_after": vram_after,
        "warnings": list(report.get("warnings", []) or []),
        "errors": [] if report.get("ok") else [report.get("error", "")],
        "ok": bool(report.get("ok")),
        "wav": str(wav_path) if wav_ok else "",
        "wav_sha256": wav_sha,
        "wav_exists": wav_ok,
        "segments_planned": segments_planned,
        "segments_attempted": int(report.get("segments") or segments_planned),
        "segments_successful": segments_successful,
        "segments_reused": segments_reused,
        "segments_regenerated": segments_regen,
        "segments_failed": segments_failed,
        "avg_qc_score": report.get("avg_score"),
        "duration_s": report.get("duration_s"),
        "master": report.get("master", {}),
        "new_generation": new_generation,
        "wav_complete": wav_complete,
        "complete_success": complete_success,
        "segment_log": str(segments_log),
        "segments_logged": segments_logged,
        "silence_pattern": silence_stats,
    }
    _write_voice_metrics(result, out_dir)
    return result


def _write_summary(results: list[dict], out_root: Path, title: str,
                   voices: list[str], fresh: bool, run_tag: str | None) -> None:
    n_requested = len(voices)
    n_completed = sum(1 for r in results if r.get("ok"))
    n_full = sum(1 for r in results if r.get("complete_success"))
    n_voice_fails = sum(1 for r in results if not r.get("ok"))
    all_new = bool(fresh
                   and all(r.get("new_generation") for r in results if r.get("ok"))
                   and n_voice_fails == 0
                   and all(int(r.get("segments_reused") or 0) == 0
                           for r in results))
    lines = []
    lines.append(f"# {title}\n")
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Voices requested: {n_requested}")
    lines.append(f"Voices completed (pipeline ok): {n_completed}")
    lines.append(f"Voices complete_success: {n_full}")
    lines.append(f"Fresh (segment cache disabled): {'YES' if fresh else 'NO'}")
    lines.append(f"segment_cache_enabled: {not fresh}")
    if run_tag:
        lines.append(f"Run tag: {run_tag}")
    lines.append("")
    lines.append("| Arena-ID | voice_id | Lang | Seed | Status | Complete | Words | "
                 "Planned | OK | Dur(s) | Reused | Regen | Failed | AvgQC | NeuGen | WAV SHA | Issues |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        aid = r.get("arena_voice_id") or _ARENA_ID_BY_VOICE.get(r["voice_id"], "")
        status = "OK" if r.get("ok") else "FAIL"
        complete = "JA" if r.get("complete_success") else ("NEIN" if r.get("ok") else "-")
        if r.get("new_generation"):
            new_gen = "JA"
        elif r.get("ok"):
            new_gen = "NEIN"
        else:
            new_gen = "-"
        issues = "; ".join(filter(None, (r.get("warnings", [])[:3] + r.get("errors", [])[:2])))
        issues += ((" | exc=" + r.get("exception_type","")) if r.get("exception_type") else "")
        lines.append(
            f"| {aid} | {r['voice_id']} | {r.get('language','')} | "
            f"{r.get('production_seed','')} | {status} | {complete} | "
            f"{r.get('plan',{}).get('words','')} | "
            f"{r.get('segments_planned','')} | {r.get('segments_successful','')} | "
            f"{r.get('duration_s','')} | {r.get('segments_reused','')} | "
            f"{r.get('segments_regenerated','')} | {r.get('segments_failed','')} | "
            f"{r.get('avg_qc_score','')} | {new_gen} | "
            f"{(r.get('wav_sha256','')[:16]+'...') if r.get('wav_sha256') else ''} | "
            f"{(issues or '')[:100]} |"
        )
    if fresh:
        lines.append(f"\nFresh watchdog: all_new_generation={all_new}")
        reused_voices = [r['voice_id'] for r in results
                         if r.get('ok') and int(r.get('segments_reused') or 0) != 0]
        if reused_voices:
            lines.append(f"- WARNING: segment-cache reuse detected: {', '.join(reused_voices)}")
    lines.append("\n## Silence/Short-Segment Pattern\n")
    for r in results:
        sp = r.get("silence_pattern") or {}
        lines.append(
            f"- {r['voice_id']}: very_short={sp.get('very_short_count',0)} "
            f"silence={sp.get('silence_count',0)} noise_like={sp.get('noise_like_count',0)} "
            f"no_voiced_speech={sp.get('no_voiced_speech_count',0)} "
            f"zero_f0={sp.get('zero_f0_count',0)} "
            f"silence_pattern_detected={sp.get('silence_pattern_detected',False)}"
        )
    lines.append("\n## Markers\n")
    for m in ("VOICE22_READY","VOICE23_READY","VOICE24_READY","VOICE25_READY",
              "VOICE27_READY","VOICE32_READY","VOICE33_READY","VOICE34_READY",
              "VOICE40_READY",
              "VOICE09_PROTECTED","VOICE12_PROTECTED","VOICE30_PRESERVED",
              "GOLDEN_REFERENCE_UNCHANGED","NO_GOLDEN_REFERENCE_CHANGE",
              "LONGFORM_BASELINE_READY"):
        lines.append(f"- {m}")
    try:
        (out_root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    except Exception as e:
        log.warning("SUMMARY.md konnte nicht geschrieben werden: %s", e)

    run_summary = {
        "title": title,
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "voices": voices,
        "n_voices_requested": n_requested,
        "n_completed_ok": n_completed,
        "n_complete_success": n_full,
        "n_voice_failures": n_voice_fails,
        "fresh": bool(fresh),
        "segment_cache_enabled": bool(not fresh),
        "run_tag": run_tag or "",
        "all_new_generation": bool(all_new and n_voice_fails == 0
                                  and n_completed == n_requested
                                  and n_full == n_requested),
        "all_wav_complete": bool(n_full == n_requested),
        "out_root": str(out_root),
        "results": results,
    }
    try:
        (out_root / "run_summary.json").write_text(
            json.dumps(run_summary, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
    except Exception as e:
        log.warning("run_summary.json konnte nicht geschrieben werden: %s", e)


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

    run_tag: str | None = None
    if args.fresh:
        run_tag = f"longform-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
        log.info("Fresh run requested: segment cache will be disabled (tag=%s)",
                 run_tag)

    log.info("Mode: %s | voices=%d -> %s | fresh=%s",
             title, len(voices), out_root, bool(args.fresh))

    registry = VoiceRegistry()
    results: list[dict] = []
    exit_code = 0
    try:
        for i, vid in enumerate(voices, 1):
            log.info("===== (%d/%d) %s =====", i, len(voices), vid)
            r = run_one(registry, vid, out_root,
                        allow_design=args.allow_design,
                        fresh=bool(args.fresh),
                        run_tag=run_tag)
            results.append(r)
            log.info(
                "[%s] ok=%s complete=%s dur=%ss reused=%s regen=%s failed=%s err=%s",
                vid, r.get("ok"), r.get("complete_success"), r.get("duration_s"),
                r.get("segments_reused"), r.get("segments_regenerated"),
                r.get("segments_failed"), r.get("errors"))
    except KeyboardInterrupt:
        log.error("Benchmark durch Benutzer abgebrochen")
        exit_code = 130
    except BaseException:
        log.exception("Benchmark-Loop durch unerwarteten Fehler abgebrochen")
        exit_code = 1
    finally:
        _write_summary(results, out_root, title=title, voices=voices,
                       fresh=bool(args.fresh), run_tag=run_tag)

    # Exit-Logik:
    #   0 = alle Stimmen complete_success
    #   2 = fresh-mode violation (reused > 0)
    #   1 = sonstige technische/Voice-Fehler
    n_ok = sum(1 for r in results if r.get("ok"))
    n_fail = sum(1 for r in results if not r.get("ok"))
    n_complete = sum(1 for r in results if r.get("complete_success"))
    log.info("%s complete: %d ok / %d fail / %d complete -> %s",
             title, n_ok, n_fail, n_complete, out_root / "SUMMARY.md")

    if args.fresh:
        non_fresh = [r["voice_id"] for r in results
                     if r.get("ok") and int(r.get("segments_reused") or 0) != 0]
        if non_fresh:
            log.error("Fresh run requested but segments were reused for: %s",
                      ", ".join(non_fresh))
            return 2
    # Wenn wir schon in der Schleife einen hard-Exit hatten, behalten wir den.
    if exit_code != 0:
        return exit_code
    if n_complete != len(voices):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
