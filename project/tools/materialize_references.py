#!/usr/bin/env python3
"""
Materialize production clone references (cache/voice_refs/{voice_id}.wav)
via the documented VoiceDesign -> Clone pipeline.

This is the ONLY sanctioned way to populate cache/voice_refs/ for voices
whose production reference is missing. It sets
VOICEOVER_ALLOW_VOICEDESIGN_MATERIALIZE=1 so runner/main.py will accept
design on this invocation; normal GUI/runtime paths NEVER auto-design.

Usage (on RTX 5060 host with Qwen3-TTS-12Hz-1.7B-VoiceDesign installed):

  # Show which voices need materialization (no GPU required):
  python project/tools/materialize_references.py --list-missing

  # Materialize one specific voice (uses recipe seed + VOICEDESIGN_REF_TEXT):
  python project/tools/materialize_references.py --voice-id en_male_warm_storytelling_authoritative_02 --language English

  # Materialize all missing production-candidate voices at once:
  python project/tools/materialize_references.py --all-missing

  # Dry-run (plan, no model load):
  python project/tools/materialize_references.py --voice-id en_male_warm_storytelling_authoritative_02 --dry-run

Reference output: project/cache/voice_refs/{candidate_id}.wav
Format: 24 kHz mono, 16-bit PCM (voice_studio.write_wav), spoken content =
VOICEDESIGN_REF_TEXT_EN/DE ("There is a book…" / "Es gibt ein Buch…").

Post-materialization the voice becomes available in the GUI; VoiceCloneEngine
will load allow_design=False (Base+Clone path, no more VoiceDesign calls).
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "project"
sys.path.insert(0, str(PROJECT))

# Enable explicit design for THIS process only
os.environ["VOICEOVER_ALLOW_VOICEDESIGN_MATERIALIZE"] = "1"


def _locate_models_dir() -> Path | None:
    if os.environ.get("VOICEOVER_MODELS_DIR"):
        p = Path(os.environ["VOICEOVER_MODELS_DIR"])
        if p.exists():
            return p
    for c in [
        PROJECT / "models",
        ROOT.parent / "VoiceOverApp-AgentReady-Latest" / "project" / "models",
        ROOT.parent.parent / "VoiceOverApp-AgentReady-Latest" / "project" / "models",
    ]:
        if c.exists() and (
            (c / "Qwen3-TTS-12Hz-1.7B-Base").exists()
            or (c / "Qwen3-TTS-12Hz-1.7B-VoiceDesign").exists()
            or (c / "hf").exists()
        ):
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


def _load_registry():
    from app.voices.registry import VoiceRegistry
    return VoiceRegistry()


def _load_recipes() -> dict:
    recipes_raw = json.loads(
        (PROJECT / "voices" / "voice_generation_recipes.json")
        .read_text(encoding="utf-8"))
    return {r["voice_id"]: r for r in recipes_raw.get("recipes", [])}


def _description_for(voice_id: str, entry, recipes: dict) -> tuple[str, str | None, str | None]:
    """Return (description, seed, language_default) for a voice, searching
    recipes → per-voice JSON → ENGLISH_VOICEDESIGN_DESCRIPTIONS → fallback."""
    from app.prosody.instruct import (ENGLISH_VOICEDESIGN_DESCRIPTIONS,
                                      VOICEDESIGN_DESCRIPTIONS)
    desc = None
    seed = None
    language = None
    if voice_id in recipes:
        r = recipes[voice_id]
        desc = r.get("voice_design_description") or r.get(
            "voice_design_prompt")
        seed = r.get("seed")
        language = r.get("language")
    # JSON file override
    jf = PROJECT / "voices" / f"{voice_id}.json"
    if jf.exists():
        d = json.loads(jf.read_text(encoding="utf-8"))
        desc = d.get("description") or desc
        s = (d.get("settings") or {}).get("seed")
        if s is not None:
            seed = s
        if not language:
            language = (d.get("settings") or {}).get("language")
            if not language:
                language = d.get("native_language")
    # Fallback: EN/DE description dicts
    desc_entry = (ENGLISH_VOICEDESIGN_DESCRIPTIONS.get(voice_id)
                  or VOICEDESIGN_DESCRIPTIONS.get(voice_id) or {})
    desc = desc_entry.get("description") or desc or entry.description
    return desc, seed, language


def list_missing():
    reg = _load_registry()
    recipes = _load_recipes()
    from app import paths as _p
    print(f"{'voice_id':50} {'lang':8} {'in_recipe':10} missing_ref")
    print("-" * 100)
    miss = []
    for e in reg.entries():
        if e.backend_mode != "clone" or e.voice_id == "vd_e":
            continue
        rp = _p.ROOT / e.reference_path if e.reference_path else None
        if rp and rp.exists() and rp.suffix.lower() == ".wav":
            continue  # already materialized
        in_recipe = "yes" if e.voice_id in recipes else "no"
        lang = e.native_language or "?"
        print(f"{e.voice_id:50} {lang:8} {in_recipe:10} {e.reference_path}")
        miss.append(e)
    print("-" * 100)
    print(f"Missing references: {len(miss)}")


def materialize(voice_id: str, language: str | None, dry_run: bool = False):
    from app import paths as _p
    from app.voices.registry import resolve_reference_text
    reg = _load_registry()
    recipes = _load_recipes()
    entry = reg.get(voice_id)
    if entry is None:
        print(f"voice_id {voice_id} not in registry", file=sys.stderr)
        sys.exit(2)
    if entry.backend_mode != "clone":
        print(f"{voice_id} is not a clone voice (backend_mode={entry.backend_mode})",
              file=sys.stderr)
        sys.exit(2)
    desc, seed, default_lang = _description_for(voice_id, entry, recipes)
    lang = language or default_lang or ("English" if voice_id.startswith("en_")
                                        else "German")
    # Use the canonical reference text registered for the voice
    # (VoiceProfileEntry.reference_text / resolve_reference_text).
    # Never hard-code per-language defaults here.
    ref_text = entry.reference_text or resolve_reference_text(
        entry.reference_text_key, lang)
    out = _p.VOICE_REFS_DIR / f"{voice_id}.wav"
    print(f"\n=== MATERIALIZE {voice_id} ===")
    print(f"  language:    {lang}")
    print(f"  seed:        {seed}")
    print(f"  description: {desc}")
    print(f"  ref_text:    {ref_text[:120]}{'…' if len(ref_text)>120 else ''}")
    print(f"  output:      {out}")
    if out.exists():
        sz = out.stat().st_size
        print(f"  EXISTS ({sz/1024:.1f} KiB, sha256={_sha256(out)[:16]}…) — skipping")
        return out
    if dry_run:
        print("  (dry-run — nothing generated)")
        return None
    # Real generation via VoiceStudio.design_reference, which writes the WAV
    try:
        import torch  # noqa: F401
    except Exception:
        print("torch/CUDA not available — cannot materialize references in "
              "this sandbox. Run on RTX 5060 host with all three Qwen models "
              "installed.", file=sys.stderr)
        sys.exit(3)
    from app.hardware.detector import detect_hardware, recommend_torch_dtype
    from app.tts.model_pool import QwenModelPool
    from app.tts.voice_studio import QwenVoiceStudio
    hw = detect_hardware()
    device = "cuda" if hw.mode.startswith("gpu") else "cpu"
    dtype = recommend_torch_dtype(hw)
    print(f"  hardware:    mode={hw.mode} device={device} dtype={dtype} "
          f"gpu={hw.gpu_name or 'none'}")
    pool = QwenModelPool(hw)
    studio = QwenVoiceStudio(pool)
    ref = studio.design_reference(candidate_id=voice_id, description=desc,
                                  language=lang, ref_text=ref_text,
                                  seed=int(seed) if seed is not None else None)
    dur = ref.wav_path.stat().st_size  # size proxy
    import wave
    with wave.open(str(ref.wav_path), "rb") as w:
        dur_s = w.getnframes() / float(w.getframerate())
    print(f"  WROTE {ref.wav_path}  ({dur_s:.2f}s, sha256={_sha256(ref.wav_path)[:16]}…)")
    return ref.wav_path


def main():
    p = argparse.ArgumentParser(description="Materialize production clone references for clone voices via VoiceDesign->WAV")
    p.add_argument("--list-missing", action="store_true")
    p.add_argument("--voice-id")
    p.add_argument("--language", choices=["English", "German"])
    p.add_argument("--all-missing", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    if args.list_missing:
        list_missing(); return
    if args.voice_id:
        materialize(args.voice_id, args.language, dry_run=args.dry_run)
        return
    if args.all_missing:
        from app import paths as _p
        reg = _load_registry()
        for e in reg.entries():
            if e.backend_mode != "clone" or e.voice_id == "vd_e":
                continue
            rp = _p.ROOT / e.reference_path if e.reference_path else None
            if rp and rp.exists() and rp.suffix.lower() == ".wav":
                continue
            materialize(e.voice_id, None, dry_run=args.dry_run)
        return
    p.print_help()


if __name__ == "__main__":
    main()
