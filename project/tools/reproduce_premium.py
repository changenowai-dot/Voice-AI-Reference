#!/usr/bin/env python3
"""
Reproduce recovered premium English AND German voices on a local RTX 5060 via
the existing Qwen VoiceDesign -> Reference WAV -> Clone Conditioning -> Base
Clone pipeline.

================================================================================
PURPOSE
================================================================================
For each recovered premium voice (EN voice-09/12/22/23/24/25/27,
DE voice-30/32/33/34), this tool:

  1. Loads the saved recipe from project/voices/voice_generation_recipes.json
  2. Runs Qwen VoiceDesign with the EXACT saved seed, description, language,
     and language-matched reference text to produce a real Qwen reference WAV
     -> project/cache/voice_refs/<voice_id>.wav
  3. Computes and records SHA256 of the reference WAV
  4. Builds a Clone Conditioning from the reference WAV via Base model
     -> project/reproduction/<voice_id>/clone_prompt.json (serialized metadata)
  5. Generates a short Qwen Clone test WAV (identical reference text) using
     the EXACT saved sampling parameters
     -> project/reproduction/<voice_id>/test_short.wav
  6. Generates the audition-comparison WAV using the LANGUAGE-MATCHED audition
     short text from the recipe (EN: "Every discovery begins with a question…";
     DE: "Jede Entdeckung beginnt mit einer Frage…")
     -> project/reproduction/<voice_id>/test_audition.wav
  7. Writes a provenance / metadata manifest
     -> project/reproduction/<voice_id>/manifest.json
     All outputs are marked status: "REPRODUCED" (never ORIGINAL_RECOVERED).
  8. NEVER modifies the Golden Reference VD-E.wav (SHA256 locked).
  9. NEVER overwrites original recipe files or arena audition MP3s.
 10. Skips voices that are already REPRODUCED with matching seed/language/
     ref_text — protects existing voice-09/voice-12 outputs.
 11. voice-34 (de_female_deep_calm_intelligent_01, status=good_archived) is
     reproduced but the recipe's human_selection.status is NEVER promoted.

================================================================================
USAGE (Windows PowerShell on RTX 5060)
================================================================================
  # 1. One-time setup (if not done yet):
  powershell -ExecutionPolicy Bypass -File project/SETUP.ps1

  # 2. Activate venv:
  .venv\Scripts\Activate.ps1
  # (or just use .venv\Scripts\python.exe directly — see reproduce_premium.ps1)

  # 3. List available voices (EN+DE, priority order):
  python project/tools/reproduce_premium.py --list

  # 4. Dry-run (no GPU, shows plan) — default: voice-09 + voice-12
  python project/tools/reproduce_premium.py --dry-run

  # 5. Reproduce the 9 remaining shortlist voices (batch, sequential,
  #    continue-on-failure, VRAM unload between voices):
  python project/tools/reproduce_premium.py --reproduce --remaining

  # 6. Post-run validation (file existence / SHA256 / manifest / recipe seeds /
  #    golden reference / validate_voices.py):
  python project/tools/reproduce_premium.py --validate --remaining

  # 7. Reproduce a specific voice (e.g., single German voice):
  python project/tools/reproduce_premium.py --reproduce --voices voice-30

  # 8. Reproduce ALL 11 voices (already-done voices skipped):
  python project/tools/reproduce_premium.py --reproduce --all

================================================================================
PREREQUISITES (must be present locally on the Windows/RTX 5060 machine)
================================================================================
  - Python 3.12.x, torch 2.11.0+cu128, transformers 4.57.3
  - qwen-tts==0.1.1  (pip install -r project/requirements.txt)
  - Models present under project/models/ or project/models/hf/hub:
      Qwen3-TTS-12Hz-1.7B-Base           (~4 GB)
      Qwen3-TTS-12Hz-1.7B-VoiceDesign    (~4 GB)
    (CustomVoice is NOT needed for this pipeline — VoiceDesign->Base Clone only)
  - NVIDIA driver supporting CUDA 12.8; RTX 5060 visible via nvidia-smi
  - ~8 GB VRAM free; models are loaded sequentially and unloaded between
    stages and between voices (VRAM guard in model_pool.unload() + gc +
    torch.cuda.empty_cache()).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import gc
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path

# Ensure project/app is importable when running from repo root or tools/
_THIS = Path(__file__).resolve()
_PROJECT_ROOT = _THIS.parents[1]          # .../project
_REPO_ROOT = _THIS.parents[2]             # .../Voice-AI-Reference
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

VOICES_DIR = _PROJECT_ROOT / "voices"
RECIPES_PATH = VOICES_DIR / "voice_generation_recipes.json"
VOICE_JSON_DIR = VOICES_DIR
CACHE_VOICE_REFS = _PROJECT_ROOT / "cache" / "voice_refs"
REPRODUCTION_DIR = _PROJECT_ROOT / "reproduction"

# Priority order as per task (voice-09 + voice-12 first, then EN remainder, then DE)
PRIORITY_ORDER = [
    ("voice-09", "en_male_warm_storytelling_authoritative_02"),
    ("voice-12", "en_male_velvet_baritone_01"),
    ("voice-22", "en_male_deep_authoritative_scholar_01"),
    ("voice-23", "en_male_mature_documentary_natural_01"),
    ("voice-24", "en_male_deep_clear_insightful_01"),
    ("voice-25", "en_male_warm_grounded_humanist_01"),
    ("voice-27", "en_male_extremely_natural_deep_conversational_01"),
    ("voice-30", "de_male_warm_storytelling_authoritative_01"),
    ("voice-32", "de_male_deep_natural_conversational_01"),
    ("voice-33", "de_female_deep_warm_documentary_01"),
    ("voice-34", "de_female_deep_calm_intelligent_01"),
]
# Remaining shortlist (i.e., the 9 voices still to reproduce for this phase)
REMAINING_SHORTLIST = [
    ("voice-22", "en_male_deep_authoritative_scholar_01"),
    ("voice-23", "en_male_mature_documentary_natural_01"),
    ("voice-24", "en_male_deep_clear_insightful_01"),
    ("voice-25", "en_male_warm_grounded_humanist_01"),
    ("voice-27", "en_male_extremely_natural_deep_conversational_01"),
    ("voice-30", "de_male_warm_storytelling_authoritative_01"),
    ("voice-32", "de_male_deep_natural_conversational_01"),
    ("voice-33", "de_female_deep_warm_documentary_01"),
    ("voice-34", "de_female_deep_calm_intelligent_01"),
]
PRIORITY_MAP = dict(PRIORITY_ORDER)      # arena_id -> voice_id
REVERSE_PRIORITY = {v: k for k, v in PRIORITY_ORDER}

# Language-default audition texts (used as fallback if recipe has no audition_text)
AUDITION_SHORT_TEXT_EN = (
    "Every discovery begins with a question. Sometimes the answer is hidden in "
    "plain sight, waiting for someone patient enough to look beyond the "
    "obvious. And when we finally understand what happened, the story is often "
    "far more fascinating than we expected."
)
AUDITION_SHORT_TEXT_DE = (
    "Jede Entdeckung beginnt mit einer Frage. Manchmal liegt die Antwort direkt "
    "vor uns, verborgen im Offensichtlichen. Doch erst wenn wir genauer "
    "hinschauen, erkennen wir, was wirklich geschehen ist. Und oft ist die "
    "Geschichte dahinter faszinierender, als wir zunaechst erwartet haben."
)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def _now_iso() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _load_recipes() -> list[dict]:
    if not RECIPES_PATH.exists():
        print(f"[ERROR] Recipe-Datei nicht gefunden: {RECIPES_PATH}", file=sys.stderr)
        sys.exit(2)
    return json.loads(RECIPES_PATH.read_text(encoding="utf-8"))["recipes"]


def _find_recipe(voice_id: str) -> dict | None:
    for r in _load_recipes():
        if r.get("voice_id") == voice_id:
            return r
    return None


def _resolve_voices(spec: str | None, use_all: bool, use_remaining: bool = False) -> list[tuple[str, str]]:
    """Return list of (arena_id, voice_id) in priority order."""
    order_index = {vid: i for i, (_, vid) in enumerate(PRIORITY_ORDER)}
    if use_all:
        return list(PRIORITY_ORDER)
    if use_remaining:
        return list(REMAINING_SHORTLIST)
    if not spec:
        return list(PRIORITY_ORDER[:2])          # default: voice-09 + voice-12
    selected = []
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        if token in PRIORITY_MAP:
            selected.append((token, PRIORITY_MAP[token]))
        elif token in REVERSE_PRIORITY:
            selected.append((REVERSE_PRIORITY[token], token))
        else:
            print(f"[WARN] Unbekannte Voice-Kennung '{token}' (erwartet z.B. voice-09 "
                  f"oder en_male_warm_storytelling_authoritative_02).", file=sys.stderr)
    # dedupe preserving order
    seen, out = set(), []
    for aid, vid in selected:
        if vid in seen:
            continue
        seen.add(vid)
        out.append((aid, vid))
    # sort by priority
    out.sort(key=lambda p: order_index.get(p[1], 99))
    return out


def _audition_text_for(r: dict) -> str:
    """Return the audition short text for a recipe.

    Prefer recipe's explicit audition_text (present for all 24 recipes); fall
    back to the language-matching default if missing.
    """
    txt = r.get("audition_text") or ""
    if txt.strip():
        return txt.strip()
    if r.get("language") == "English":
        return AUDITION_SHORT_TEXT_EN
    return AUDITION_SHORT_TEXT_DE


def _load_existing_manifest(voice_id: str) -> dict | None:
    mpath = REPRODUCTION_DIR / voice_id / "manifest.json"
    if not mpath.exists():
        return None
    try:
        return json.loads(mpath.read_text(encoding="utf-8"))
    except Exception:
        return None


def _manifest_matches_recipe(m: dict, r: dict) -> bool:
    """Return True iff the existing manifest appears complete and matches the
    recipe's seed/language/voice_id/reference_text — i.e. it represents a
    successful reproduction we can safely skip."""
    try:
        if m.get("status") != "REPRODUCED":
            return False
        if m.get("seed") != int(r.get("seed")):
            return False
        if m.get("language") != r.get("language"):
            return False
        if m.get("voice_id") != r.get("voice_id"):
            return False
        if m.get("reference_text") != r.get("voicedesign_reference_text"):
            return False
        out_dir = REPRODUCTION_DIR / r["voice_id"]
        for rel in ("reference_voicedesign.wav", "test_short.wav",
                    "test_audition.wav", "manifest.json", "clone_prompt.json"):
            if not (out_dir / rel).exists():
                return False
        outputs = m.get("outputs") or {}
        if "test_short" not in outputs or "test_audition" not in outputs:
            return False
        if not outputs["test_short"].get("sha256"):
            return False
        if not outputs["test_audition"].get("sha256"):
            return False
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Dry-run / Plan
# ---------------------------------------------------------------------------
def cmd_list() -> None:
    recipes = _load_recipes()
    by_vid = {r["voice_id"]: r for r in recipes}
    print("\nPremium Voices (priority order — EN first, then DE):\n")
    print(f"{'Rank':<5} {'Arena-ID':<10} {'voice_id':<55} {'Lang':<8} {'Seed':<7} {'Status'}")
    print("-" * 115)
    for i, (aid, vid) in enumerate(PRIORITY_ORDER, start=1):
        r = by_vid.get(vid, {})
        seed = r.get("seed", "?")
        hs = (r.get("human_selection") or {}).get("status", "?")
        lang = r.get("language", "?")
        print(f"{i:<5} {aid:<10} {vid:<55} {str(lang):<8} {str(seed):<7} {hs}")
    print()


def cmd_dry_run(voices: list[tuple[str, str]]) -> None:
    print("\n=== REPRODUCTION PLAN (dry-run) — no GPU / no models loaded ===\n")
    for aid, vid in voices:
        r = _find_recipe(vid)
        if not r:
            print(f"[ERROR] Kein Rezept für {vid}", file=sys.stderr)
            continue
        out_dir = REPRODUCTION_DIR / vid
        ref_wav = CACHE_VOICE_REFS / f"{vid}.wav"
        print(f"--- {aid}  {vid} ---")
        print(f"  Seed:                 {r['seed']}")
        print(f"  Language:             {r['language']}")
        print(f"  VoiceDesign Instruct: {r['voice_design_description']}")
        print(f"  Reference Text:       \"{r['voicedesign_reference_text']}\"")
        print(f"  Sampling (balanced):  {r['voice_design_parameters'].get('sampling')}")
        print(f"  Output directory:     {out_dir}")
        print(f"  Reference WAV:        {ref_wav}")
        print(f"  Clone Prompt meta:    {out_dir / 'clone_prompt.json'}")
        print(f"  Short test WAV:       {out_dir / 'test_short.wav'}")
        print(f"  Manifest:             {out_dir / 'manifest.json'}")
        print(f"  Provenance:           REPRODUCED (not ORIGINAL_RECOVERED)")
        print()
    print("Run with --reproduce on the RTX 5060 machine (with models installed)\n"
          "to actually invoke Qwen VoiceDesign -> Clone.")


# ---------------------------------------------------------------------------
# Real reproduction (RTX 5060)
# ---------------------------------------------------------------------------
def _check_environment() -> tuple[bool, str]:
    """Return (ok, message).  ok=True means CUDA torch+qwen_tts are usable."""
    try:
        import torch  # noqa
    except Exception as e:
        return False, f"torch nicht importierbar: {e}"
    try:
        import qwen_tts  # noqa
    except Exception as e:
        return False, f"qwen_tts nicht importierbar: {e}"
    import torch
    if not torch.cuda.is_available():
        return False, "CUDA nicht verfügbar (torch.cuda.is_available()=False)."
    return True, f"CUDA verfügbar: {torch.cuda.get_device_name(0)}"


def _reproduce_one(aid: str, vid: str, r: dict, long_text: str | None,
                   skip_if_exists: bool, force: bool = False) -> dict:
    """Reproduce a single premium voice. Returns manifest dict.

    If skip_if_exists is True AND all expected output files already exist
    (reference WAV, test_short.wav, test_audition.wav, manifest.json with
    status=REPRODUCED, seed/language/voice_id matching the recipe), this
    returns the existing manifest without re-running Qwen — protecting
    already-successful outputs like voice-09/voice-12.
    """
    import numpy as np
    import torch

    out_dir = REPRODUCTION_DIR / vid
    out_dir.mkdir(parents=True, exist_ok=True)

    # The reference WAV path (written by design_reference below; we never
    # overwrite existing VD-E — different name).
    ref_wav_path = CACHE_VOICE_REFS / f"{vid}.wav"

    # Short-circuit: if everything already produced and recipe matches, skip
    existing = _load_existing_manifest(vid)
    if skip_if_exists and existing and _manifest_matches_recipe(existing, r):
        print(f"\n[{_now_iso()}] === Skipping {aid}  {vid} (already REPRODUCED, matches recipe) ===")
        return existing

    # Honest: print header
    print(f"\n[{_now_iso()}] === Reproducing {aid}  {vid} (seed={r['seed']}, lang={r['language']}) ===")
    print(f"  Instruct:  {r['voice_design_description']}")
    print(f"  Ref-text:  \"{r['voicedesign_reference_text']}\"")
    print(f"  Audition:  \"{_audition_text_for(r)[:80]}...\"")

    # Decide whether to run VoiceDesign from scratch.
    if force:
        need_design = True
        print(f"  [force] Reference WAV wird neu erzeugt (--force): {ref_wav_path}")
        CACHE_VOICE_REFS.mkdir(parents=True, exist_ok=True)
    elif ref_wav_path.exists():
        need_design = False
        if skip_if_exists:
            print(f"  [skip] Reference WAV existiert bereits (wird wiederverwendet): {ref_wav_path}")
        else:
            print(f"  [info] Reference WAV existiert (wird wiederverwendet trotz --no-skip-existing, um die VD-Phase nicht zu wiederholen): {ref_wav_path}")
    else:
        need_design = True
        print(f"  [info] Keine Reference WAV vorhanden; VoiceDesign wird ausgeführt: {ref_wav_path}")
        CACHE_VOICE_REFS.mkdir(parents=True, exist_ok=True)

    # ---- Import project modules (after project is on sys.path) ----
    from app.hardware.detector import detect_hardware
    from app.tts.model_pool import QwenModelPool
    from app.tts.voice_studio import QwenVoiceStudio, VoiceRef
    from app.tts.engine_base import SynthesisRequest
    from app.tts.sampler import params_for_set, max_new_tokens_for
    from app.audio.io import write_wav, read_wav

    hw = detect_hardware()
    print(f"  Hardware:  {hw}")

    pool = QwenModelPool(hw)
    studio = QwenVoiceStudio(pool)

    runtime = {
        "python": platform.python_version(),
        "torch": torch.__version__,
        "cuda": torch.version.cuda or "n/a",
        "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
        "platform": platform.platform(),
    }
    print(f"  Runtime:   {runtime}")

    # ==============================================================
    # STEP 1 — VoiceDesign -> Reference WAV
    # ==============================================================
    t_step = time.perf_counter()
    # need_design was computed above but may have been overridden by force flag
    if need_design or force:
        print("  [1/4] Running Qwen VoiceDesign to create reference WAV...")
        ref = studio.design_reference(
            candidate_id=vid,
            description=r["voice_design_description"],
            language=r["language"],
            ref_text=r["voicedesign_reference_text"],
            seed=int(r["seed"]),
        )
    else:
        print(f"  [1/4] Reusing existing reference WAV: {ref_wav_path}")
        ref = VoiceRef(candidate_id=vid,
                       description=r["voice_design_description"],
                       ref_text=r["voicedesign_reference_text"],
                       wav_path=ref_wav_path,
                       language=r["language"])
    step1_dur = time.perf_counter() - t_step
    ref_sha = _sha256_file(ref.wav_path)
    ref_size = ref.wav_path.stat().st_size
    with open(ref.wav_path, "rb") as f:
        _ = f.read(44)  # skip WAV header
        # Quick duration via soundfile or fallback
    try:
        _wav_data, ref_sr = read_wav(ref.wav_path)
        ref_dur = round(float(len(_wav_data) / ref_sr), 3)
    except Exception:
        _wav_data, ref_sr, ref_dur = None, None, None
    print(f"        -> {ref.wav_path}  ({ref_size} bytes, {ref_dur}s @ {ref_sr}Hz)"
          if ref_dur else f"        -> {ref.wav_path}  ({ref_size} bytes)")
    print(f"         SHA256: {ref_sha}")
    print(f"         step1 took {step1_dur:.1f}s")

    # Copy reference WAV into reproduction folder (for archival; never modify
    # the canonical cache/voice_refs copy).
    ref_copy = out_dir / "reference_voicedesign.wav"
    ref_copy.write_bytes(ref.wav_path.read_bytes())

    # ==============================================================
    # STEP 2 — Build Clone Conditioning (Base model)
    # ==============================================================
    t_step = time.perf_counter()
    print("  [2/4] Building Clone Conditioning (Base model create_voice_clone_prompt)...")
    # Unload VoiceDesign model first to free VRAM on 8 GB card
    pool.unload()
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    prompt = studio.build_clone_prompt(ref)
    step2_dur = time.perf_counter() - t_step
    print(f"         Clone prompt built (type={type(prompt).__name__})")
    print(f"         step2 took {step2_dur:.1f}s")

    # Serialize metadata about the clone prompt (we do not attempt to pickle
    # the actual tensor prompt across runs — that would be brittle. The prompt
    # is rebuilt at runtime from the reference WAV, which is identified by SHA256.)
    clone_meta = {
        "created": _now_iso(),
        "voice_id": vid,
        "arena_voice_id": aid,
        "reference_wav": str(ref.wav_path.relative_to(_PROJECT_ROOT)),
        "reference_sha256": ref_sha,
        "reference_text": ref.ref_text,
        "description": ref.description,
        "language": ref.language,
        "prompt_type": str(type(prompt).__name__),
        "note": ("Clone prompt is a runtime object returned by "
                 "Qwen3TTSModel.create_voice_clone_prompt(ref_audio, ref_text). "
                 "It is deterministically reproducible from the reference WAV "
                 "(SHA256 above), so we persist only metadata — not the tensor.")
    }
    (out_dir / "clone_prompt.json").write_text(
        json.dumps(clone_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # ==============================================================
    # STEP 3 — Short test synthesis (identical reference text, ~15s)
    # ==============================================================
    t_step = time.perf_counter()
    sampling = dict(r["sampling_parameters"])  # do_sample/temperature/top_k/top_p/rep_penalty
    short_text = r["voicedesign_reference_text"]
    # Estimate duration: ~15s reference text, plus headroom
    max_sec = 25.0
    req_short = SynthesisRequest(
        text=short_text,
        language=r["language"],
        speaker=vid,
        instruct="",
        sampling=sampling,
        seed=int(r["seed"]),
        max_seconds_hint=max_sec,
    )
    print(f"  [3/4] Synthesizing SHORT test WAV ({len(short_text)} chars, "
          f"seed={req_short.seed}, sampling={sampling})...")
    # Ensure deterministic seed
    torch.manual_seed(int(r["seed"]))
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(int(r["seed"]))
    res_short = studio.synth_clone(prompt, req_short)
    step3_dur = time.perf_counter() - t_step
    short_path = out_dir / "test_short.wav"
    write_wav(short_path, res_short.waveform, res_short.sample_rate, bit_depth=16)
    short_sha = _sha256_file(short_path)
    print(f"        -> {short_path}  ({short_path.stat().st_size} bytes, "
          f"{res_short.duration_s}s @ {res_short.sample_rate}Hz)")
    print(f"         SHA256: {short_sha}, RTF={res_short.realtime_factor}")
    print(f"         step3 took {step3_dur:.1f}s")

    # ==============================================================
    # STEP 4 — Audition short-text synthesis (human comparison text)
    # ==============================================================
    t_step = time.perf_counter()
    audition_text = _audition_text_for(r)
    req_aud = SynthesisRequest(
        text=audition_text,
        language=r["language"],
        speaker=vid,
        instruct="",
        sampling=sampling,
        # Offset seed deterministically from the recipe seed; use same offset
        # across all voices so existing voice-09/voice-12 outputs remain
        # byte-reproducible (they used seed+1).
        seed=int(r["seed"]) + 1,
        max_seconds_hint=30.0 if r["language"] == "English" else 35.0,
    )
    print(f"  [4/4] Synthesizing AUDITION comparison WAV ({len(audition_text)} chars, "
          f"seed={req_aud.seed})...")
    torch.manual_seed(req_aud.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(req_aud.seed)
    res_aud = studio.synth_clone(prompt, req_aud)
    step4_dur = time.perf_counter() - t_step
    aud_path = out_dir / "test_audition.wav"
    write_wav(aud_path, res_aud.waveform, res_aud.sample_rate, bit_depth=16)
    aud_sha = _sha256_file(aud_path)
    print(f"        -> {aud_path}  ({aud_path.stat().st_size} bytes, "
          f"{res_aud.duration_s}s @ {res_aud.sample_rate}Hz)")
    print(f"         SHA256: {aud_sha}")
    print(f"         step4 took {step4_dur:.1f}s")

    # ==============================================================
    # Optional: long text
    # ==============================================================
    long_info = None
    if long_text:
        t_step = time.perf_counter()
        long_path = out_dir / "test_long.wav"
        est_sec = max(30.0, len(long_text) / 14.0)  # ~14 chars/s rough
        req_long = SynthesisRequest(
            text=long_text,
            language=r["language"],
            speaker=vid,
            instruct="",
            sampling=sampling,
            seed=int(r["seed"]) + 2,
            max_seconds_hint=est_sec + 10.0,
        )
        print(f"  [+]   Synthesizing LONG text ({len(long_text)} chars, "
              f"seed={req_long.seed}, est ~{est_sec:.0f}s)...")
        torch.manual_seed(req_long.seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(req_long.seed)
        res_long = studio.synth_clone(prompt, req_long)
        write_wav(long_path, res_long.waveform, res_long.sample_rate, bit_depth=16)
        long_sha = _sha256_file(long_path)
        long_dur = time.perf_counter() - t_step
        long_info = {
            "path": str(long_path.relative_to(_PROJECT_ROOT)),
            "sha256": long_sha,
            "chars": len(long_text),
            "duration_s": res_long.duration_s,
            "elapsed_s": round(long_dur, 2),
            "sample_rate": res_long.sample_rate,
            "seed": req_long.seed,
        }
        print(f"        -> {long_path}  ({long_path.stat().st_size} bytes, "
              f"{res_long.duration_s}s)")
        print(f"         step took {long_dur:.1f}s")

    # Cleanup: unload models to free VRAM for next voice
    pool.unload()
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # ==============================================================
    # Manifest
    # ==============================================================
    manifest = {
        "schema_version": 1,
        "status": "REPRODUCED",
        "status_note": ("Reproduced locally via Qwen VoiceDesign -> Base Clone. "
                        "NOT the original Arena audition audio. "
                        "Recipe, seed, description, and reference text were "
                        "taken verbatim from the recovered recipe."),
        "created": _now_iso(),
        "voice_id": vid,
        "arena_voice_id": aid,
        "human_selection": r.get("human_selection", {}),
        "recipe_source": str(RECIPES_PATH.relative_to(_REPO_ROOT)),
        "seed": int(r["seed"]),
        "language": r["language"],
        "gender": r["gender"],
        "voice_design_description": r["voice_design_description"],
        "reference_text": r["voicedesign_reference_text"],
        "sampling_parameters": sampling,
        "reference_wav": {
            "path": str(ref.wav_path.relative_to(_PROJECT_ROOT)),
            "sha256": ref_sha,
            "size_bytes": ref_size,
            "sample_rate": ref_sr,
            "duration_s": ref_dur,
            "design_elapsed_s": round(step1_dur, 2),
        },
        "clone_conditioning": {
            "metadata_path": "clone_prompt.json",
            "build_elapsed_s": round(step2_dur, 2),
        },
        "outputs": {
            "test_short": {
                "path": str(short_path.relative_to(_PROJECT_ROOT)),
                "sha256": short_sha,
                "text": short_text,
                "seed": req_short.seed,
                "duration_s": res_short.duration_s,
                "sample_rate": res_short.sample_rate,
                "elapsed_s": round(step3_dur, 2),
                "realtime_factor": res_short.realtime_factor,
            },
            "test_audition": {
                "path": str(aud_path.relative_to(_PROJECT_ROOT)),
                "sha256": aud_sha,
                "text": audition_text,
                "seed": req_aud.seed,
                "duration_s": res_aud.duration_s,
                "sample_rate": res_aud.sample_rate,
                "elapsed_s": round(step4_dur, 2),
                "realtime_factor": res_aud.realtime_factor,
            },
        },
        "runtime": runtime,
        "original_arena_audition_mp3": r.get("reference_audio_path"),
        "original_arena_audition_note": r.get("provenance_note", ""),
    }
    if long_info:
        manifest["outputs"]["test_long"] = long_info

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  [DONE] Manifest: {out_dir / 'manifest.json'}")
    return manifest


def cmd_reproduce(voices: list[tuple[str, str]], long_text: str | None,
                  skip_if_exists: bool, force: bool = False) -> int:
    ok, msg = _check_environment()
    print(f"[env] {msg}")
    if not ok:
        print("\n[ABORT] Die lokale Qwen-Umgebung ist nicht bereit. "
              "Führe zuerst project/SETUP.ps1 aus und stelle sicher, dass "
              "die RTX 5060 und die Qwen-Modelle unter project/models/ "
              "verfügbar sind.", file=sys.stderr)
        return 3

    results = []
    failures = []
    skipped = []
    for i, (aid, vid) in enumerate(voices, start=1):
        print(f"\n++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
        print(f"  ({i}/{len(voices)}) {aid}  {vid}")
        print(f"++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
        r = _find_recipe(vid)
        if not r:
            failures.append((aid, vid, "recipe not found"))
            print(f"[FAIL] Rezept für {vid} nicht gefunden.")
            continue
        # Protect VD-E from accidental reproduction through this tool
        if vid == "vd_e":
            print(f"[SKIP] vd_e ist die GOLDEN REFERENCE und darf über dieses "
                  "Tool NICHT neu erzeugt werden.")
            continue
        # Detect complete prior reproduction and skip (protect voice-09/voice-12)
        if skip_if_exists and not force:
            existing = _load_existing_manifest(vid)
            if existing and _manifest_matches_recipe(existing, r):
                skipped.append((aid, vid, "already REPRODUCED (matches recipe)"))
                print(f"[SKIP] {aid} {vid} — already REPRODUCED with matching recipe; leaving outputs untouched.")
                results.append((aid, vid, existing))
                continue
        try:
            m = _reproduce_one(aid, vid, r, long_text, skip_if_exists, force=force)
            results.append((aid, vid, m))
        except Exception as e:
            import traceback
            traceback.print_exc()
            failures.append((aid, vid, str(e)))
            print(f"[FAIL] {vid}: {e}", file=sys.stderr)
            # attempt to unload models to recover VRAM for next voice
            try:
                import torch, gc
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

    # Summary
    print("\n============================================================")
    print("REPRODUCTION SUMMARY")
    print("============================================================")
    for aid, vid, _ in skipped:
        print(f"  SKIP {aid:<10} {vid:<55} already REPRODUCED (untouched)")
    for aid, vid, m in results:
        if (aid, vid) in {(a, v) for a, v, _ in skipped}:
            continue
        ref = m["reference_wav"]
        short = m["outputs"]["test_short"]
        print(f"  OK   {aid:<10} {vid:<55} "
              f"ref_sha={ref['sha256'][:16]}... "
              f"short_dur={short['duration_s']}s")
    for aid, vid, err in failures:
        print(f"  FAIL {aid:<10} {vid:<55} {err}")
    print()
    print(f"Outputs under: {REPRODUCTION_DIR}")
    print(f"Reference WAVs under: {CACHE_VOICE_REFS}")
    return 0 if not failures else 1


# ---------------------------------------------------------------------------
# Post-run validation
# ---------------------------------------------------------------------------
def cmd_validate(voices: list[tuple[str, str]]) -> int:
    """Validate that each voice has all expected outputs, SHA256s, manifests
    match recipes, Golden Reference untouched, and recipes were not modified.
    """
    import importlib.util
    # Validate golden reference
    problems: list[str] = []
    golden = _PROJECT_ROOT / "VD-E_GOLDEN_REFERENCE" / "VD-E.wav"
    expected_golden_sha = "B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025"
    print("\n=== POST-RUN VALIDATION ===\n")
    if golden.exists():
        sha = _sha256_file(golden)
        ok = sha == expected_golden_sha
        print(f"  [{'OK' if ok else 'FAIL'}] Golden Reference SHA256: {sha[:16]}...")
        if not ok:
            problems.append(f"Golden Reference SHA mismatch (got {sha}, expected {expected_golden_sha})")
    else:
        print(f"  [FAIL] Golden Reference missing at {golden}")
        problems.append("Golden Reference missing")

    # Per-voice checks
    print()
    for aid, vid in voices:
        r = _find_recipe(vid)
        print(f"--- {aid}  {vid} ---")
        out_dir = REPRODUCTION_DIR / vid
        ref_wav = CACHE_VOICE_REFS / f"{vid}.wav"
        for rel, label in [
            ("reference_voicedesign.wav", "reference_voicedesign.wav"),
            ("test_short.wav", "test_short.wav"),
            ("test_audition.wav", "test_audition.wav"),
            ("clone_prompt.json", "clone_prompt.json"),
            ("manifest.json", "manifest.json"),
        ]:
            p = out_dir / rel
            ok = p.exists()
            print(f"  [{'OK' if ok else 'MISS'}] {p}")
            if not ok:
                problems.append(f"{vid}: {label} missing")
        # Ref cache
        ok = ref_wav.exists()
        print(f"  [{'OK' if ok else 'MISS'}] cache/voice_refs/{vid}.wav")
        if not ok:
            problems.append(f"{vid}: cache reference WAV missing")
        # Manifest content
        m = _load_existing_manifest(vid)
        if m:
            for field in ("status", "seed", "language", "voice_id",
                          "reference_text", "reference_wav", "outputs"):
                ok = field in m
                print(f"  [{'OK' if ok else 'MISS'}] manifest.{field}")
                if not ok:
                    problems.append(f"{vid}: manifest missing '{field}'")
            if m.get("status") != "REPRODUCED":
                print(f"  [WARN] manifest.status = {m.get('status')} (expected REPRODUCED)")
                # Not a hard fail for voice-34 which may be archived, but flag it.
            if r:
                if not _manifest_matches_recipe(m, r):
                    msg = (f"{vid}: manifest does not match recipe (seed/lang/voice_id/"
                           f"ref_text or SHA256 missing)")
                    print(f"  [WARN] {msg}")
                    problems.append(msg)
                else:
                    print(f"  [OK]   manifest matches recipe (seed={m.get('seed')},"
                          f" lang={m.get('language')})")
                # voice-34 preservation: recipe status must NOT be auto-promoted
                # by this tool (we never write to recipes, so this is a safety
                # assertion against accidental mutation elsewhere).
                if vid == "de_female_deep_calm_intelligent_01":
                    hs_status = (r.get("human_selection") or {}).get("status")
                    # This tool must NOT promote voice-34 to e.g. locked_human_favorite
                    if hs_status in ("locked_human_favorite", "saved_human_shortlist_promoted"):
                        problems.append(
                            f"{vid}: recipe human_selection.status was auto-promoted to "
                            f"{hs_status} — this tool must NOT do that.")
                    else:
                        print(f"  [OK]   recipe human_selection.status = '{hs_status}'"
                              f" (preserved — not auto-promoted by this tool)")
            # SHA256 present in manifest outputs
            outputs = m.get("outputs") or {}
            for key in ("test_short", "test_audition"):
                o = outputs.get(key) or {}
                sha_ok = bool(o.get("sha256"))
                print(f"  [{'OK' if sha_ok else 'MISS'}] manifest.outputs.{key}.sha256")
                if not sha_ok:
                    problems.append(f"{vid}: outputs.{key}.sha256 missing")
            # Cross-check actual file SHA against recorded SHA
            for key, fname in (("test_short", "test_short.wav"),
                              ("test_audition", "test_audition.wav")):
                o = outputs.get(key) or {}
                rec = o.get("sha256")
                fpath = out_dir / fname
                if rec and fpath.exists():
                    actual = _sha256_file(fpath)
                    match = actual == rec
                    print(f"  [{'OK' if match else 'FAIL'}] SHA256 cross-check {fname}: {match}")
                    if not match:
                        problems.append(f"{vid}: {fname} SHA mismatch (manifest={rec[:16]},"
                                        f" actual={actual[:16]})")
        else:
            problems.append(f"{vid}: manifest.json unreadable")
        print()

    # Voice-09 / voice-12 not-overwritten check (heuristic: manifest seed/lang intact)
    for aid, vid in (("voice-09", "en_male_warm_storytelling_authoritative_02"),
                     ("voice-12", "en_male_velvet_baritone_01")):
        m = _load_existing_manifest(vid)
        if m:
            print(f"  [OK]   {aid} existing manifest present (untouched): "
                  f"status={m.get('status')} seed={m.get('seed')}")
        else:
            print(f"  [INFO] {aid} has no prior reproduction manifest (first run OK)")

    # Run project-level validate_voices.py if available
    vv = _PROJECT_ROOT / "tools" / "validate_voices.py"
    if vv.exists():
        print("\n--- Running project/tools/validate_voices.py ---")
        try:
            import subprocess
            res = subprocess.run([sys.executable, str(vv)],
                                 cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=60)
            print(res.stdout)
            if res.returncode != 0:
                print(res.stderr)
                problems.append(f"validate_voices.py exited with code {res.returncode}")
        except Exception as e:
            problems.append(f"validate_voices.py could not run: {e}")

    # Recipe modification check (recipes must NOT have been altered). We verify
    # the recipes still contain the expected seeds for the 11 target voices.
    expected_seeds = {vid: seed for _, (vid, seed) in []}  # populated below
    expected_seeds = {
        "en_male_warm_storytelling_authoritative_02": 52018,
        "en_male_velvet_baritone_01": 52021,
        "en_male_deep_authoritative_scholar_01": 52031,
        "en_male_mature_documentary_natural_01": 52032,
        "en_male_deep_clear_insightful_01": 52033,
        "en_male_warm_grounded_humanist_01": 52034,
        "en_male_extremely_natural_deep_conversational_01": 52036,
        "de_male_warm_storytelling_authoritative_01": 53003,
        "de_male_deep_natural_conversational_01": 53005,
        "de_female_deep_warm_documentary_01": 53011,
        "de_female_deep_calm_intelligent_01": 53012,
    }
    print("\n--- Recipe seed integrity check ---")
    for vid, expected_seed in expected_seeds.items():
        r = _find_recipe(vid)
        if not r:
            problems.append(f"{vid}: recipe missing")
            print(f"  [FAIL] {vid}: recipe missing")
            continue
        actual = r.get("seed")
        ok = int(actual) == int(expected_seed)
        print(f"  [{'OK' if ok else 'FAIL'}] {vid}: seed={actual} (expected {expected_seed})")
        if not ok:
            problems.append(f"{vid}: seed changed ({actual} vs {expected_seed})")

    print("\n============================================================")
    print("VALIDATION SUMMARY")
    print("============================================================")
    if problems:
        print(f"  {len(problems)} problem(s) found:")
        for p in problems:
            print(f"    - {p}")
        return 1
    print("  ALL CHECKS PASSED")
    return 0


def cmd_batch(voices: list[tuple[str, str]], long_text: str | None,
              skip_if_exists: bool, force: bool, python_exe: str) -> int:
    """Process voices sequentially, one SUBPROCESS per voice, to guarantee full
    CUDA / torch / model-pool teardown between voices on an 8 GB RTX 5060.

    Continues on individual failure and prints a final report.
    """
    import subprocess
    script = str(_THIS)
    results = []
    failures = []
    skipped = []
    total = len(voices)
    print(f"\n=== BATCH MODE — {total} voices, one subprocess per voice ===\n")
    for i, (aid, vid) in enumerate(voices, start=1):
        # Pre-check if already REPRODUCED (avoid spawning subprocess at all)
        r = _find_recipe(vid)
        if r and skip_if_exists and not force:
            existing = _load_existing_manifest(vid)
            if existing and _manifest_matches_recipe(existing, r):
                skipped.append((aid, vid))
                print(f"[{i}/{total}] SKIP {aid} {vid} (already REPRODUCED)")
                results.append((aid, vid, 0, "skip"))
                continue
        print(f"\n[{i}/{total}] >>> Starting {aid} {vid}")
        cmd = [python_exe, script, "--reproduce", "--voices", aid]
        if force:
            cmd.append("--force")
        if not skip_if_exists:
            cmd.append("--no-skip-existing")
        if long_text:
            cmd.extend(["--long-text", long_text])
        t0 = time.perf_counter()
        try:
            proc = subprocess.run(cmd, cwd=str(_REPO_ROOT))
            rc = proc.returncode
        except Exception as e:
            rc = -1
            print(f"  subprocess error: {e}")
        dur = time.perf_counter() - t0
        if rc == 0:
            print(f"[{i}/{total}] <<< OK   {aid} {vid}  ({dur:.0f}s)")
            results.append((aid, vid, rc, f"ok ({dur:.0f}s)"))
        else:
            print(f"[{i}/{total}] <<< FAIL {aid} {vid}  rc={rc} ({dur:.0f}s)")
            failures.append((aid, vid, f"exit code {rc}"))
            results.append((aid, vid, rc, f"FAIL rc={rc}"))

    print("\n============================================================")
    print("BATCH SUMMARY")
    print("============================================================")
    for aid, vid, rc, note in results:
        tag = "OK  " if rc == 0 else "FAIL"
        if note == "skip":
            tag = "SKIP"
        print(f"  {tag} {aid:<10} {vid:<55} {note}")
    print()
    print(f"Outputs under: {REPRODUCTION_DIR}")
    print(f"Reference WAVs under: {CACHE_VOICE_REFS}")
    return 0 if not failures else 1


def main() -> int:
    p = argparse.ArgumentParser(
        description="Reproduce recovered premium EN+DE voices on local RTX 5060 "
                    "(VoiceDesign -> Reference WAV -> Clone Conditioning -> Base Clone). "
                    "Supports single-voice, in-process sequential, and per-voice "
                    "subprocess batch processing (recommended for 8 GB VRAM).")
    p.add_argument("--list", action="store_true", help="Premium voices auflisten")
    p.add_argument("--dry-run", action="store_true", help="Plan anzeigen ohne GPU")
    p.add_argument("--reproduce", action="store_true", help="Echte Qwen-Synthese (RTX 5060)")
    p.add_argument("--batch", action="store_true",
                   help="Wie --reproduce, aber pro Voice ein eigener Subprocess "
                        "(empfohlen für RTX 5060 8 GB — CUDA/Torch werden nach jeder "
                        "Stimme komplett freigegeben).")
    p.add_argument("--validate", action="store_true",
                   help="Post-run Validierung: Dateien/Hashes/Manifeste/Rezepte prüfen")
    p.add_argument("--voices", type=str, default=None,
                   help="Kommagetrennte Liste von Arena-IDs (voice-09,voice-12,...) "
                        "oder voice_ids. Ohne Angabe: voice-09+voice-12 (Priorität 1).")
    p.add_argument("--all", action="store_true", help="Alle 11 Premium-Stimmen (EN+DE)")
    p.add_argument("--remaining", action="store_true",
                   help="Die 9 noch fehlenden Stimmen (EN voice-22/23/24/25/27 + "
                        "DE voice-30/32/33/34) — Standard-Batch für diese Phase")
    p.add_argument("--long-text", type=str, default=None,
                   help="Optionaler langer Testtext (Datei @pfad oder String)")
    p.add_argument("--no-skip-existing", action="store_true",
                   help="Bereits vorhandene Reference WAVs NICHT überspringen "
                        "(VoiceDesign-Phase läuft erneut; ohne --force werden "
                        "aber bereits komplett reproduzierte Stimmen weiterhin "
                        "übersprungen).")
    p.add_argument("--force", action="store_true",
                   help="Auch komplett reproduzierte Stimmen neu erzeugen "
                        "(überschreibt Referenz-WAV und Ausgaben; VORSICHT).")
    p.add_argument("--python", type=str, default=sys.executable,
                   help="Pfad zu python.exe im venv (nur für --batch relevant; "
                        "default: aktueller Interpreter).")
    args = p.parse_args()

    if args.list:
        cmd_list()
        return 0

    voices = _resolve_voices(args.voices, args.all, use_remaining=args.remaining)

    # Load long-text
    long_text = args.long_text
    if long_text and long_text.startswith("@"):
        long_path = Path(long_text[1:])
        if not long_path.is_absolute():
            long_path = _REPO_ROOT / long_path
        long_text = long_path.read_text(encoding="utf-8").strip()

    if args.validate:
        return cmd_validate(voices)
    if args.dry_run:
        cmd_dry_run(voices)
        # If batch+dry-run, also show the batch execution plan
        if args.batch:
            print("\n=== BATCH PLAN (one subprocess per voice, sequential, continue-on-failure) ===")
            for i, (aid, vid) in enumerate(voices, start=1):
                r = _find_recipe(vid) or {}
                status_label = ("SKIP (already REPRODUCED)"
                                if _load_existing_manifest(vid)
                                   and _manifest_matches_recipe(_load_existing_manifest(vid), r)
                                else "RUN")
                print(f"  {i:>2}. [{status_label}] {aid}  {vid}  (seed={r.get('seed')}, lang={r.get('language')})")
            print()
            print(f"Per-voice command: {args.python} {_THIS} --reproduce --voices <id>")
            print("Between voices: process exits -> full CUDA/torch/model-pool teardown.")
        return 0
    if args.batch:
        return cmd_batch(voices, long_text,
                         skip_if_exists=not args.no_skip_existing,
                         force=args.force,
                         python_exe=args.python)
    if args.reproduce:
        return cmd_reproduce(voices, long_text,
                             skip_if_exists=not args.no_skip_existing,
                             force=args.force)
    # Default behavior (no mode flags): show dry-run plan
    cmd_dry_run(voices)
    return 0


if __name__ == "__main__":
    sys.exit(main())
