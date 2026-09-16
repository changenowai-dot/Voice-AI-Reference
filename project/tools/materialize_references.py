#!/usr/bin/env python3
"""
Materialize production clone references (cache/voice_refs/{voice_id}.wav)
via the documented VoiceDesign -> Clone pipeline.

This is the ONLY sanctioned way to populate cache/voice_refs/ for voices
whose production reference is missing or whose existing bundle fails
validation. It sets VOICEOVER_ALLOW_VOICEDESIGN_MATERIALIZE=1 so
runner/main.py will accept design on this invocation; normal GUI/runtime
paths NEVER auto-design.

Post-materialization the WAV is accompanied by an atomic
<wav>.wav.json reference-bundle manifest (see
app/tts/reference_bundle.py). Existing WAVs are NOT skipped merely
because they exist:

  WAV exists + manifest exists + valid   -> VALID; leave alone
  WAV exists + manifest missing          -> deterministic bootstrap via
                                            recipe/provenance (same logic
                                            as bootstrap_reference_bundles)
  WAV exists + manifest invalid          -> hard error; do not overwrite
                                            silently. Pass --force to
                                            regenerate.
  WAV missing                            -> generate via VoiceDesign and
                                            write WAV + manifest
                                            atomically.

Usage (on RTX 5060 host with Qwen3-TTS-12Hz-1.7B-VoiceDesign installed):

  # Show which voices need materialization (no GPU required):
  python project/tools/materialize_references.py --list-missing

  # Materialize / repair one specific voice:
  python project/tools/materialize_references.py --voice-id en_male_warm_storytelling_authoritative_02 --language English

  # Materialize all missing production-candidate voices at once:
  python project/tools/materialize_references.py --all-missing

  # Dry-run (plan, no model load):
  python project/tools/materialize_references.py --voice-id en_male_warm_storytelling_authoritative_02 --dry-run

Reference output: project/cache/voice_refs/{candidate_id}.wav
Format: 24 kHz mono, 16-bit PCM (voice_studio.write_wav), spoken content =
the voice's canonical reference text (recipe/VOICEDESIGN_REF_TEXT_EN/DE).

Post-materialization the voice becomes available in the GUI; VoiceCloneEngine
will load allow_design=False (Base+Clone path, no more VoiceDesign calls).
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "project"
sys.path.insert(0, str(PROJECT))

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


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _load_registry():
    from app.voices.registry import VoiceRegistry
    return VoiceRegistry()


def _load_recipes() -> dict:
    recipes_raw = json.loads(
        (PROJECT / "voices" / "voice_generation_recipes.json")
        .read_text(encoding="utf-8"))
    return {r["voice_id"]: r for r in recipes_raw.get("recipes", [])}


def _ast_load_descriptions():
    """Return (en_dict, de_dict) parsed lazily from prosody/instruct.py.

    We AST-parse instead of importing so that --list-missing / sidecar
    repair work on hosts without numpy/torch installed.
    """
    import ast as _ast
    _inst = PROJECT / "app" / "prosody" / "instruct.py"
    en_dict: dict = {}
    de_dict: dict = {}
    if not _inst.exists():
        return en_dict, de_dict
    try:
        tree = _ast.parse(_inst.read_text(encoding="utf-8"))
    except Exception:
        return en_dict, de_dict
    for node in tree.body:
        if isinstance(node, _ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, _ast.Name):
                    if tgt.id == "ENGLISH_VOICEDESIGN_DESCRIPTIONS":
                        try: en_dict = _ast.literal_eval(node.value)
                        except Exception: pass
                    elif tgt.id == "VOICEDESIGN_DESCRIPTIONS":
                        try: de_dict = _ast.literal_eval(node.value)
                        except Exception: pass
    return en_dict, de_dict


def _description_for(voice_id: str, entry, recipes: dict) -> tuple[str, int | None, str | None]:
    """Return (description, seed, language_default) for a voice."""
    desc = None
    seed = None
    language = None
    if voice_id in recipes:
        r = recipes[voice_id]
        desc = r.get("voice_design_description") or r.get(
            "voice_design_prompt")
        seed = r.get("seed")
        language = r.get("language")
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
    en_dict, de_dict = _ast_load_descriptions()
    desc_entry = en_dict.get(voice_id) or de_dict.get(voice_id) or {}
    desc = desc_entry.get("description") or desc or entry.description or ""
    return desc, seed, language


def _voice_language(voice_id: str, voice_json_lang: str | None) -> str:
    if voice_json_lang in ("English", "German"):
        return voice_json_lang
    if voice_id.startswith("en_"):
        return "English"
    return "German"


def _git_commit() -> str | None:
    import subprocess
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                           capture_output=True, timeout=5, check=False)
        if r.returncode == 0:
            return r.stdout.decode().strip()
    except Exception:
        pass
    return None


def _prove_canonical_text(voice_id: str, entry, recipe, lang: str,
                          requested_ref_text: str | None) -> str:
    """Determine the exact canonical reference text for this voice.

    Resolution order (fail-closed; never guess):
      1. Explicit --ref-text CLI argument (advanced only).
      2. recipe.voicedesign_reference_text
      3. recipe.voice_design_parameters.ref_text
      4. entry.reference_text (registry-resolved; already resolved from
         symbolic keys by the registry).
      5. language default VOICEDESIGN_REF_TEXT_EN/DE when the entry's
         reference_text_key is the symbolic constant pointing to it.
    """
    from app.tts.reference_bundle import default_ref_text_for
    default_txt = default_ref_text_for(lang)
    if requested_ref_text and requested_ref_text.strip():
        return requested_ref_text.strip()
    if recipe:
        t = recipe.get("voicedesign_reference_text")
        if t and t.strip():
            return t.strip()
        vdp = recipe.get("voice_design_parameters") or {}
        t = vdp.get("ref_text")
        if t and t.strip():
            return t.strip()
    if entry.reference_text and entry.reference_text.strip():
        return entry.reference_text.strip()
    if entry.reference_text_key in ("VOICEDESIGN_REF_TEXT_EN",
                                    "VOICEDESIGN_REF_TEXT_DE"):
        return default_txt
    raise RuntimeError(
        f"REFERENCE_BUNDLE_PROVENANCE_UNPROVABLE for {voice_id}\n"
        "Cannot determine the exact reference transcript from the voice "
        "recipe / profile. Refusing to materialize with a guessed text.")


def _write_manifest_for_existing_wav(voice_id: str, wav: Path, ref_text: str,
                                     lang: str, seed: int | None,
                                     desc: str) -> Path:
    from app.tts.reference_bundle import (ReferenceBundle,
                                          write_bundle_atomically)
    audio_sha = _sha256(wav)
    text_sha = _sha256_text(ref_text)
    bundle = ReferenceBundle(
        voice_id=voice_id,
        audio_path=wav,
        audio_sha256=audio_sha,
        reference_text=ref_text,
        reference_text_sha256=text_sha,
        language=lang,
        generation={
            "seed": int(seed) if seed is not None else None,
            "model": "Qwen3-TTS-12Hz-1.7B-VoiceDesign",
            "model_version": "unknown",
            "engine_version": "qwen-voicestudio-v1",
            "source_commit": _git_commit(),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "description": desc,
            "bootstrapped_by": "tools/materialize_references.py",
            "note": ("Manifest back-filled against existing canonical WAV; "
                     "WAV was NOT re-synthesized."),
        },
    )
    ok, summ, _ = bundle.validate()
    if not ok:
        raise RuntimeError(
            f"Cannot build bundle for existing WAV - constructed bundle "
            f"is invalid:\n{summ}")
    return write_bundle_atomically(bundle)


def list_missing():
    from app import paths as _p
    from app.tts.reference_bundle import manifest_path_for, load_bundle
    reg = _load_registry()
    recipes = _load_recipes()
    print(f"{'voice_id':55} {'lang':8} {'in_recipe':10} status")
    print("-" * 110)
    for e in reg.entries():
        if e.backend_mode != "clone" or e.voice_id == "vd_e":
            continue
        wav = _p.VOICE_REFS_DIR / f"{e.voice_id}.wav"
        in_recipe = "yes" if e.voice_id in recipes else "no"
        lang = "English" if e.voice_id.startswith("en_") else "German"
        mp = manifest_path_for(wav)
        if not wav.exists():
            status = "WAV_MISSING"
        elif not mp.exists():
            status = "WAV_EXISTS_MANIFEST_MISSING"
        else:
            b = load_bundle(wav, voice_id=e.voice_id)
            if b is None:
                status = "MANIFEST_UNREADABLE"
            else:
                ok, _, _ = b.validate()
                status = "VALID" if ok else "BUNDLE_INVALID"
        print(f"{e.voice_id:55} {lang:8} {in_recipe:10} {status}")


def materialize(voice_id: str, language: str | None, dry_run: bool = False,
                force: bool = False, ref_text_override: str | None = None):
    from app import paths as _p
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
    desc, recipe_seed, _ = _description_for(voice_id, entry, recipes)
    if language is not None:
        lang = language
    else:
        s_lang = None
        try:
            s_lang = (json.loads((PROJECT / "voices" / f"{voice_id}.json")
                                 .read_text(encoding="utf-8"))
                      .get("settings") or {}).get("language")
        except Exception:
            s_lang = None
        lang = _voice_language(voice_id, s_lang)
    seed = recipe_seed
    try:
        ref_text = _prove_canonical_text(voice_id, entry,
                                         recipes.get(voice_id), lang,
                                         ref_text_override)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        sys.exit(4)

    out = _p.VOICE_REFS_DIR / f"{voice_id}.wav"
    mp = out.with_name(out.name + ".json")
    _p.VOICE_REFS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n=== MATERIALIZE {voice_id} ===")
    print(f"  language:    {lang}")
    print(f"  seed:        {seed}")
    print(f"  description: {desc}")
    print(f"  ref_text:    {ref_text[:120]}{'...' if len(ref_text)>120 else ''}")
    print(f"  output wav:  {out}")
    print(f"  output manifest: {mp}")

    from app.tts.reference_bundle import load_bundle, resolve_bundle
    if out.exists():
        if mp.exists() and not force:
            b = load_bundle(out, voice_id=voice_id)
            if b is not None:
                ok, summ, _ = b.validate()
                if ok:
                    print(f"  VALID - bundle intact; bundle_id={b.bundle_id()} "
                          f"audio_sha={b.audio_sha256[:16]}... "
                          f"text_sha={b.reference_text_sha256[:16]}...")
                    if b.reference_text.strip() != ref_text.strip():
                        print("  WARNING: bundle text differs from current "
                              "recipe. Bundle left intact; pass --force to "
                              "regenerate.", file=sys.stderr)
                    return out
                print("  BUNDLE_INVALID:\n" + summ, file=sys.stderr)
                print("  Refusing to overwrite an invalid manifest "
                      "without --force.", file=sys.stderr)
                sys.exit(5)
            print("  MANIFEST_UNREADABLE - refusing to overwrite "
                  "without --force.", file=sys.stderr)
            if not force:
                sys.exit(5)
        elif not mp.exists():
            print(f"  EXISTS ({out.stat().st_size/1024:.1f} KiB, "
                  f"sha256={_sha256(out)[:16]}...), manifest MISSING - "
                  "writing atomic sidecar from proven recipe.")
            if dry_run:
                print("  (dry-run - would write sidecar)")
                return None
            mp_written = _write_manifest_for_existing_wav(
                voice_id, out, ref_text, lang, seed, desc)
            try:
                rb = resolve_bundle(voice_id, language=lang,
                                    require_manifest=(voice_id != "vd_e"))
            except Exception as e:                    # noqa: BLE001
                print(f"  POST-WRITE VALIDATION FAILED: {e}", file=sys.stderr)
                sys.exit(6)
            print(f"  WROTE {mp_written}  (bundle_id={rb.bundle_id()}, "
                  f"audio_sha={rb.audio_sha256[:16]}..., "
                  f"text_sha={rb.reference_text_sha256[:16]}...)")
            return out

    if dry_run:
        if out.exists():
            print("  (dry-run - would regenerate WAV+manifest; force=%s)" % force)
        else:
            print("  (dry-run - would generate WAV+manifest)")
        return None

    try:
        import torch  # noqa: F401
    except Exception:
        print("torch/CUDA not available - cannot materialize references in "
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
    import wave
    with wave.open(str(ref.wav_path), "rb") as w:
        dur_s = w.getnframes() / float(w.getframerate())
    print(f"  WROTE {ref.wav_path}  ({dur_s:.2f}s, sha256={_sha256(ref.wav_path)[:16]}...)")
    rb = resolve_bundle(voice_id, language=lang,
                        require_manifest=(voice_id != "vd_e"))
    print(f"  bundle_id={rb.bundle_id()} audio_sha={rb.audio_sha256[:16]}... "
          f"text_sha={rb.reference_text_sha256[:16]}...")
    return ref.wav_path


def main():
    p = argparse.ArgumentParser(description="Materialize production clone references for clone voices via VoiceDesign->WAV")
    p.add_argument("--list-missing", action="store_true")
    p.add_argument("--voice-id")
    p.add_argument("--language", choices=["English", "German"])
    p.add_argument("--ref-text", default=None,
                   help="Advanced: override the reference transcript.")
    p.add_argument("--all-missing", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true",
                   help="Regenerate WAV+manifest even when an existing "
                        "(invalid) bundle is present.")
    args = p.parse_args()
    if args.list_missing:
        list_missing(); return
    if args.voice_id:
        materialize(args.voice_id, args.language, dry_run=args.dry_run,
                    force=args.force, ref_text_override=args.ref_text)
        return
    if args.all_missing:
        from app import paths as _p
        reg = _load_registry()
        for e in reg.entries():
            if e.backend_mode != "clone" or e.voice_id == "vd_e":
                continue
            wav = _p.VOICE_REFS_DIR / f"{e.voice_id}.wav"
            mp = wav.with_name(wav.name + ".json")
            if wav.exists() and mp.exists():
                try:
                    from app.tts.reference_bundle import load_bundle
                    b = load_bundle(wav, voice_id=e.voice_id)
                    if b is not None:
                        ok, _, _ = b.validate()
                        if ok:
                            continue
                except Exception:
                    pass
            materialize(e.voice_id, None, dry_run=args.dry_run,
                        force=args.force, ref_text_override=args.ref_text)
        return
    p.print_help()


if __name__ == "__main__":
    main()
