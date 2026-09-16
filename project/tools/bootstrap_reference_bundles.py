#!/usr/bin/env python3
"""Bootstrap atomic .wav.json reference manifests for existing production
clone references.

Problem addressed
-----------------
Clone references materialized *before* the atomic reference-bundle
architecture exist on disk as a lone ``cache/voice_refs/<id>.wav`` with
no sidecar manifest. After the bundle hardening, those voices would be
refused (REFERENCE_BUNDLE_MANIFEST_MISSING) even though their audio is
valid. This script walks the registry and, for every clone voice whose
canonical WAV exists and whose recipe declares the standard
VOICEDESIGN_REF_TEXT_EN/DE transcript, writes a .wav.json sidecar with
the correct audio/text hashes.

Run on the GPU host:

    python project/tools/bootstrap_reference_bundles.py --dry-run
    python project/tools/bootstrap_reference_bundles.py            # write

The script refuses to bootstrap a voice whose recipe declares a non-
standard (custom) reference text, because in that case we cannot prove
the WAV matches any specific transcript and the only safe option is to
re-materialize via tools/materialize_references.py.

VD-E is handled by the runtime bootstrap inside resolve_bundle() and
does NOT need a sidecar (we never touch the Golden WAV), but we will
still write one for hygiene if --include-vde is passed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "project"))


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


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


def _recipe_for(voice_id: str) -> dict | None:
    p = ROOT / "project" / "voices" / "voice_generation_recipes.json"
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    for r in data.get("recipes", []):
        if r.get("voice_id") == voice_id:
            return r
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include-vde", action="store_true",
                    help="Also write a sidecar for VD-E (Golden WAV left "
                         "untouched; we only add metadata next to it).")
    args = ap.parse_args()

    from app import paths
    from app.voices.registry import VoiceRegistry
    from app.tts.reference_bundle import (default_ref_text_for,
                                          manifest_path_for)

    reg = VoiceRegistry()
    bootstrapped = []
    skipped = []
    for e in reg.entries():
        if e.backend_mode != "clone":
            continue
        if e.voice_id == "vd_e" and not args.include_vde:
            skipped.append((e.voice_id, "Golden VD-E uses runtime bootstrap"))
            continue
        wav = paths.ROOT / e.reference_path if e.reference_path else None
        if not wav or not wav.exists():
            skipped.append((e.voice_id, "WAV missing"))
            continue
        mp = manifest_path_for(wav)
        if mp.exists():
            skipped.append((e.voice_id, "manifest already exists"))
            continue

        # Only auto-bootstrap when the recipe/reference_text is the
        # standard default for the voice's language. Otherwise we can't
        # prove the transcript matches.
        lang = "English" if e.voice_id.startswith("en_") else \
               "German" if e.voice_id.startswith("de_") or e.voice_id == "vd_e" \
               else None
        default_txt = default_ref_text_for(lang) if lang else None
        recipe = _recipe_for(e.voice_id)
        recipe_txt = None
        if recipe:
            recipe_txt = recipe.get("voicedesign_reference_text") or \
                (recipe.get("voice_design_parameters") or {}).get("ref_text")
        # Confirm recipe/entry uses the standard default text key or the
        # literal default text.
        accepted_txt = None
        if e.reference_text_key in ("VOICEDESIGN_REF_TEXT_EN",
                                    "VOICEDESIGN_REF_TEXT_DE", None):
            accepted_txt = default_txt
        elif e.reference_text and default_txt and \
                e.reference_text.strip() == default_txt.strip():
            accepted_txt = default_txt
        elif recipe_txt and default_txt and \
                recipe_txt.strip() == default_txt.strip():
            accepted_txt = default_txt
        if accepted_txt is None:
            skipped.append((e.voice_id,
                            "ref_text is non-default — cannot prove match; "
                            "re-materialize with materialize_references.py"))
            continue

        recipe_seed = None
        if recipe:
            recipe_seed = recipe.get("seed")
        settings_seed = None
        try:
            settings_seed = int((json.loads(
                (ROOT / "project" / "voices" / f"{e.voice_id}.json")
                .read_text(encoding="utf-8")).get("settings") or {}).get("seed"))
        except Exception:
            settings_seed = None

        manifest = {
            "schema_version": 1,
            "voice_id": e.voice_id,
            "reference_audio": {
                "path": wav.name,
                "sha256": sha256_file(wav),
            },
            "reference_text": {
                "text": accepted_txt,
                "sha256": sha256_text(accepted_txt),
            },
            "language": lang,
            "generation": {
                "seed": recipe_seed if recipe_seed is not None else settings_seed,
                "model": "Qwen3-TTS-12Hz-1.7B-VoiceDesign",
                "model_version": "unknown",
                "engine_version": "qwen-voicestudio-v1",
                "source_commit": _git_commit(),
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "description": (recipe.get("voice_design_description")
                                if recipe else "") or e.description or "",
                "bootstrapped_by": "tools/bootstrap_reference_bundles.py",
                "note": "Manifest back-filled from canonical default "
                        "VOICEDESIGN_REF_TEXT + on-disk WAV hash.",
            },
        }
        print(f"[{'DRYRUN' if args.dry_run else 'WRITE'}] {e.voice_id:55} "
              f"audio_sha={manifest['reference_audio']['sha256'][:16]}… "
              f"text_sha={manifest['reference_text']['sha256'][:16]}…")
        if not args.dry_run:
            mp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                          encoding="utf-8")
        bootstrapped.append(e.voice_id)

    print(f"\nBootstrapped: {len(bootstrapped)}")
    for v, why in skipped:
        print(f"  skipped: {v} — {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
