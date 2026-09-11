#!/usr/bin/env python3
"""
Reproduce the recovered premium English voices on a local RTX 5060 via the
existing Qwen VoiceDesign -> Reference WAV -> Clone Conditioning -> Base Clone
pipeline.

================================================================================
PURPOSE
================================================================================
For each of the 7 recovered premium voices (voice-09, voice-12, voice-22..27),
this tool:

  1. Loads the saved recipe from project/voices/voice_generation_recipes.json
  2. Runs Qwen VoiceDesign with the EXACT saved seed, description, and
     reference text to produce a real Qwen reference WAV
     -> project/cache/voice_refs/<voice_id>.wav
  3. Computes and records SHA256 of the reference WAV
  4. Builds a Clone Conditioning from the reference WAV via Base model
     -> project/reproduction/<voice_id>/clone_prompt.json (serialized metadata)
  5. Generates a short Qwen Clone test WAV (identical reference text + the
     audition short text) using the EXACT saved sampling parameters
     -> project/reproduction/<voice_id>/test_short.wav
  6. Generates an optional longer test WAV if --long-text is supplied
     -> project/reproduction/<voice_id>/test_long.wav
  7. Writes a provenance / metadata manifest
     -> project/reproduction/<voice_id>/manifest.json
     All outputs are marked status: "REPRODUCED" (never ORIGINAL_RECOVERED).
  8. NEVER modifies the Golden Reference VD-E.wav.
  9. NEVER overwrites original recipe files or arena audition MP3s.

================================================================================
USAGE (Windows PowerShell on RTX 5060)
================================================================================
  # 1. One-time setup (if not done yet):
  powershell -ExecutionPolicy Bypass -File project/SETUP.ps1

  # 2. Activate venv:
  .venv\Scripts\Activate.ps1
  # (or just use .venv\Scripts\python.exe directly — see reproduce_premium.ps1)

  # 3. List available voices:
  python project/tools/reproduce_premium.py --list

  # 4. Dry-run (no GPU, shows plan):
  python project/tools/reproduce_premium.py --dry-run --voices voice-09,voice-12

  # 5. Reproduce voice-09 and voice-12 (the locked human favorites) — priority 1:
  python project/tools/reproduce_premium.py --reproduce --voices voice-09,voice-12

  # 6. Reproduce all 7 shortlist voices:
  python project/tools/reproduce_premium.py --reproduce --all

  # 7. Reproduce with a longer custom test:
  python project/tools/reproduce_premium.py --reproduce --voices voice-09 ^
      --long-text "In 1914, Europe descended into a war that would redraw every border..."

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
    stages (VRAM guard already in model_pool.unload()).
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

# Priority order as per task
PRIORITY_ORDER = [
    ("voice-09", "en_male_warm_storytelling_authoritative_02"),
    ("voice-12", "en_male_velvet_baritone_01"),
    ("voice-22", "en_male_deep_authoritative_scholar_01"),
    ("voice-23", "en_male_mature_documentary_natural_01"),
    ("voice-24", "en_male_deep_clear_insightful_01"),
    ("voice-25", "en_male_warm_grounded_humanist_01"),
    ("voice-27", "en_male_extremely_natural_deep_conversational_01"),
]
PRIORITY_MAP = dict(PRIORITY_ORDER)      # arena_id -> voice_id
REVERSE_PRIORITY = {v: k for k, v in PRIORITY_ORDER}

# Audition short text used for the fast-audition round (human evaluation)
AUDITION_SHORT_TEXT_EN = (
    "Every discovery begins with a question. Sometimes the answer is hidden in "
    "plain sight, waiting for someone patient enough to look beyond the "
    "obvious. And when we finally understand what happened, the story is often "
    "far more fascinating than we expected."
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


def _resolve_voices(spec: str | None, use_all: bool) -> list[tuple[str, str]]:
    """Return list of (arena_id, voice_id) in priority order."""
    order_index = {vid: i for i, (_, vid) in enumerate(PRIORITY_ORDER)}
    if use_all:
        return list(PRIORITY_ORDER)
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


# ---------------------------------------------------------------------------
# Dry-run / Plan
# ---------------------------------------------------------------------------
def cmd_list() -> None:
    recipes = _load_recipes()
    by_vid = {r["voice_id"]: r for r in recipes}
    print("\nPremium English Voices (in priority order):\n")
    print(f"{'Rank':<5} {'Arena-ID':<10} {'voice_id':<55} {'Seed':<7} {'Status'}")
    print("-" * 110)
    for i, (aid, vid) in enumerate(PRIORITY_ORDER, start=1):
        r = by_vid.get(vid, {})
        seed = r.get("seed", "?")
        hs = (r.get("human_selection") or {}).get("status", "?")
        print(f"{i:<5} {aid:<10} {vid:<55} {str(seed):<7} {hs}")
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
                   skip_if_exists: bool) -> dict:
    """Reproduce a single premium voice. Returns manifest dict."""
    import numpy as np
    import torch

    out_dir = REPRODUCTION_DIR / vid
    out_dir.mkdir(parents=True, exist_ok=True)

    # The reference WAV path (written by design_reference below; we never
    # overwrite existing VD-E — different name).
    ref_wav_path = CACHE_VOICE_REFS / f"{vid}.wav"

    # Honest: print header
    print(f"\n[{_now_iso()}] === Reproducing {aid}  {vid} (seed={r['seed']}) ===")
    print(f"  Instruct:  {r['voice_design_description']}")
    print(f"  Ref-text:  \"{r['voicedesign_reference_text']}\"")

    if skip_if_exists and ref_wav_path.exists():
        print(f"  [skip] Reference WAV existiert bereits: {ref_wav_path}")
        # Load existing ref; still build clone prompt from it.
    else:
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
    need_design = not ref_wav_path.exists()
    if need_design:
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
    audition_text = AUDITION_SHORT_TEXT_EN
    req_aud = SynthesisRequest(
        text=audition_text,
        language=r["language"],
        speaker=vid,
        instruct="",
        sampling=sampling,
        seed=int(r["seed"]) + 1,  # offset seed to avoid deterministic collision
        max_seconds_hint=30.0,
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
                  skip_if_exists: bool) -> int:
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
        if r.get("provenance") == "actual_qwen" and vid == "vd_e":
            continue
        try:
            m = _reproduce_one(aid, vid, r, long_text, skip_if_exists)
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
    for aid, vid, m in results:
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


def main() -> int:
    p = argparse.ArgumentParser(
        description="Reproduce recovered premium English voices on local RTX 5060 "
                    "(VoiceDesign -> Reference WAV -> Clone Conditioning -> Base Clone)")
    p.add_argument("--list", action="store_true", help="Premium voices auflisten")
    p.add_argument("--dry-run", action="store_true", help="Plan anzeigen ohne GPU")
    p.add_argument("--reproduce", action="store_true", help="Echte Qwen-Synthese (RTX 5060)")
    p.add_argument("--voices", type=str, default=None,
                   help="Kommagetrennte Liste von Arena-IDs (voice-09,voice-12,...) "
                        "oder voice_ids. Ohne Angabe: voice-09+voice-12 (Priorität 1).")
    p.add_argument("--all", action="store_true", help="Alle 7 Premium-Stimmen")
    p.add_argument("--long-text", type=str, default=None,
                   help="Optionaler langer Testtext (datei @pfad oder String)")
    p.add_argument("--no-skip-existing", action="store_true",
                   help="Bereits vorhandene Reference WAVs neu erzeugen "
                        "(default: überspringen und nur neu klonen)")
    args = p.parse_args()

    if args.list:
        cmd_list()
        return 0

    voices = _resolve_voices(args.voices, args.all)

    # Load long-text
    long_text = args.long_text
    if long_text and long_text.startswith("@"):
        long_path = Path(long_text[1:])
        if not long_path.is_absolute():
            long_path = _REPO_ROOT / long_path
        long_text = long_path.read_text(encoding="utf-8").strip()

    if args.reproduce:
        return cmd_reproduce(voices, long_text, skip_if_exists=not args.no_skip_existing)
    cmd_dry_run(voices)
    return 0


if __name__ == "__main__":
    sys.exit(main())
