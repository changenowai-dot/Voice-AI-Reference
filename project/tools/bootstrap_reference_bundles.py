#!/usr/bin/env python3
"""Bootstrap atomic .wav.json reference manifests for existing production
clone references.

This is a REPAIR tool for the transition to the atomic ReferenceBundle
architecture. It does NOT synthesize audio and does NOT overwrite any
existing WAV or existing valid manifest.

Three outcomes per voice:

  ALREADY_VALID             - WAV + manifest present, validate() passes.
                              Nothing is written.
  WOULD_CREATE_MANIFEST / CREATED_MANIFEST
                            - WAV exists, manifest missing, and the
                              voice's documented recipe uses the
                              canonical default VOICEDESIGN_REF_TEXT_EN/DE
                              so the transcript can be proven. The
                              sidecar is written atomically and then
                              reloaded through resolve_bundle() to
                              confirm.
  SKIPPED (reason)          - missing WAV / VD-E / non-default recipe
                              text (cannot prove provenance) / invalid
                              existing manifest. In the latter case the
                              tool refuses to overwrite silently - use
                              materialize_references.py --force to
                              regenerate, or delete the corrupt manifest
                              and re-run.

Run on the GPU host:

    python project/tools/bootstrap_reference_bundles.py --dry-run
    python project/tools/bootstrap_reference_bundles.py

VD-E is handled by the runtime bootstrap inside resolve_bundle() and
does NOT need a sidecar. Pass --include-vde to write one for hygiene;
the Golden WAV itself is never touched.
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


def _resolve_canonical_wav(entry, paths) -> Path:
    """Return the canonical WAV path for a VoiceProfileEntry.

    The canonical location is always paths.VOICE_REFS_DIR / f"{voice_id}.wav"
    (per the ReferenceBundle contract). If the entry's configured
    reference_path resolves to something else we DO NOT use it - that's
    a misconfiguration that resolve_bundle() will flag as non-canonical
    at synthesis time.
    """
    return paths.VOICE_REFS_DIR / f"{entry.voice_id}.wav"


def _voice_language(entry) -> str | None:
    if entry.voice_id.startswith("en_"):
        return "English"
    if entry.voice_id.startswith("de_") or entry.voice_id == "vd_e":
        return "German"
    return None


def _prove_canonical_text(entry, recipe, default_txt: str | None) -> str | None:
    """Return the provably-correct reference transcript for ``entry``
    or None if provenance cannot be established without guessing.

    Proof rules (any is sufficient):
      * entry.reference_text_key is the symbolic constant
        VOICEDESIGN_REF_TEXT_EN/DE  -> default_txt
      * entry.reference_text resolves to default_txt verbatim
      * recipe.voicedesign_reference_text == default_txt verbatim
      * recipe.voice_design_parameters.ref_text == default_txt verbatim
    """
    if not default_txt:
        return None
    if entry.reference_text_key in ("VOICEDESIGN_REF_TEXT_EN",
                                    "VOICEDESIGN_REF_TEXT_DE"):
        return default_txt
    if entry.reference_text and \
            entry.reference_text.strip() == default_txt.strip():
        return default_txt
    if recipe:
        rt = recipe.get("voicedesign_reference_text")
        if rt and rt.strip() == default_txt.strip():
            return default_txt
        vdp = recipe.get("voice_design_parameters") or {}
        rt2 = vdp.get("ref_text")
        if rt2 and rt2.strip() == default_txt.strip():
            return default_txt
    return None


def _try_existing_manifest(bundle_cls, wav: Path, voice_id: str):
    """If a sidecar exists, load+validate. Returns (bundle, status_str)."""
    from app.tts.reference_bundle import load_bundle
    mp = wav.with_name(wav.name + ".json")
    if not mp.exists():
        return None, "missing"
    b = load_bundle(wav, voice_id=voice_id)
    if b is None:
        return None, "unreadable"
    ok, _summary, _detail = b.validate()
    if ok:
        return b, "valid"
    return b, "invalid"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include-vde", action="store_true",
                    help="Also write a sidecar for VD-E (Golden WAV left "
                         "untouched; only metadata is added).")
    args = ap.parse_args()

    from app import paths
    from app.voices.registry import VoiceRegistry
    from app.tts.reference_bundle import (ReferenceBundle,
                                          default_ref_text_for,
                                          write_bundle_atomically,
                                          resolve_bundle)

    reg = VoiceRegistry()
    created: list[str] = []
    already_valid: list[str] = []
    skipped: list[tuple[str, str]] = []

    for e in reg.entries():
        if e.backend_mode != "clone":
            continue
        if e.voice_id == "vd_e" and not args.include_vde:
            skipped.append((e.voice_id, "Golden VD-E uses runtime bootstrap"))
            continue

        wav = _resolve_canonical_wav(e, paths)
        if not wav.exists():
            skipped.append((e.voice_id, "canonical WAV missing"))
            continue

        existing, status = _try_existing_manifest(ReferenceBundle, wav, e.voice_id)
        if status == "valid":
            already_valid.append(e.voice_id)
            continue
        if status in ("invalid", "unreadable"):
            skipped.append((e.voice_id,
                            f"existing manifest {status} - refusing to "
                            "overwrite; run materialize_references.py or "
                            "delete the corrupt sidecar manually"))
            continue
        # status == "missing" -> attempt deterministic bootstrap
        lang = _voice_language(e)
        default_txt = default_ref_text_for(lang) if lang else None
        recipe = _recipe_for(e.voice_id)
        proven_text = _prove_canonical_text(e, recipe, default_txt)
        if proven_text is None:
            skipped.append((e.voice_id,
                            "REFERENCE_BUNDLE_PROVENANCE_UNPROVABLE: "
                            "voice recipe does not resolve to a canonical "
                            "default ref_text; cannot safely create sidecar. "
                            "Re-materialize via tools/materialize_references.py"))
            continue

        seed = (recipe.get("seed") if recipe else None)
        if seed is None:
            try:
                jf = ROOT / "project" / "voices" / f"{e.voice_id}.json"
                seed = int((json.loads(jf.read_text(encoding="utf-8"))
                            .get("settings") or {}).get("seed"))
            except Exception:
                seed = None
        desc = ((recipe.get("voice_design_description") if recipe else None)
                or e.description or "")

        audio_sha = sha256_file(wav)
        text_sha = sha256_text(proven_text)

        bundle = ReferenceBundle(
            voice_id=e.voice_id,
            audio_path=wav,
            audio_sha256=audio_sha,
            reference_text=proven_text,
            reference_text_sha256=text_sha,
            language=lang or "English",
            generation={
                "seed": int(seed) if seed is not None else None,
                "model": "Qwen3-TTS-12Hz-1.7B-VoiceDesign",
                "model_version": "unknown",
                "engine_version": "qwen-voicestudio-v1",
                "source_commit": _git_commit(),
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "description": desc,
                "bootstrapped_by": "tools/bootstrap_reference_bundles.py",
                "note": ("Manifest back-filled from canonical "
                         "VOICEDESIGN_REF_TEXT + on-disk WAV SHA. "
                         "WAV was NOT re-synthesized."),
            },
        )
        ok, summ, _ = bundle.validate()
        if not ok:
            skipped.append((e.voice_id,
                            "constructed bundle does not validate: " + summ))
            continue

        verb = "WOULD_CREATE_MANIFEST" if args.dry_run else "CREATED_MANIFEST"
        print(f"[{verb}] {e.voice_id:55} "
              f"audio_sha={audio_sha[:16]}... text_sha={text_sha[:16]}... "
              f"lang={lang} seed={seed}")
        if not args.dry_run:
            write_bundle_atomically(bundle)
            reloaded = resolve_bundle(e.voice_id, language=lang,
                                      require_manifest=(e.voice_id != "vd_e"))
            if reloaded.audio_sha256 != audio_sha or \
               reloaded.reference_text_sha256 != text_sha:
                skipped.append((e.voice_id,
                                "post-write resolver returned different "
                                "hashes - NOT reporting success"))
                continue
            created.append(e.voice_id)
        else:
            created.append(e.voice_id)

    print()
    print(f"Already valid: {len(already_valid)}")
    for v in already_valid:
        print(f"  ALREADY_VALID {v}")
    label = "Would create" if args.dry_run else "Created"
    print(f"{label}: {len(created)}")
    for v in created:
        print(f"  {'WOULD_CREATE_MANIFEST' if args.dry_run else 'CREATED_MANIFEST'} {v}")
    print(f"Skipped: {len(skipped)}")
    for v, why in skipped:
        print(f"  SKIPPED {v} - {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
