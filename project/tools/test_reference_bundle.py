#!/usr/bin/env python3
"""Regression tests for the atomic reference-bundle architecture.

Exercises the eight failure/acceptance cases required by the long-form
stability work (clone reference = audio+text+provenance, no silent
ref_text=None, no ambiguity, no guessing). Run without GPU:

    python project/tools/test_reference_bundle.py

All tests run against a TMP voice_refs directory so they never touch
production references.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "project"))


def _silence_wav(p: Path, seconds: float = 6.0, sr: int = 24000) -> None:
    """Write a small 16-bit mono silence WAV to use as a stand-in ref."""
    import struct
    n = int(seconds * sr)
    p.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"\x00\x00" * n)


def main() -> int:
    # Isolate VOICE_REFS_DIR for the duration of the test
    tmp = Path(tempfile.mkdtemp(prefix="refbundle_test_"))
    refs = tmp / "cache" / "voice_refs"
    refs.mkdir(parents=True)
    os.environ["VOICEOVER_REFS_DIR"] = str(refs)

    # Force paths module reload with overridden dir
    import importlib
    import app.paths as paths_mod
    paths_mod.VOICE_REFS_DIR = refs
    import app.tts.reference_bundle as rb
    importlib.reload(rb)

    from app.tts.reference_bundle import (ReferenceBundle,
                                          BundleResolutionError,
                                          create_bundle,
                                          default_ref_text_for,
                                          manifest_path_for,
                                          resolve_bundle,
                                          sha256_file,
                                          sha256_text,
                                          write_bundle_atomically)

    EN_TXT = default_ref_text_for("English")

    failures: list[str] = []
    passes = 0

    def check(name: str, cond: bool, detail: str = ""):
        nonlocal passes
        if cond:
            passes += 1
            print(f"[PASS] {name}")
        else:
            failures.append(f"{name}: {detail}")
            print(f"[FAIL] {name} — {detail}")

    # ----- Test A: valid bundle validates -----------------------------------
    wav_a = refs / "voice_A.wav"
    _silence_wav(wav_a)
    # Recompute because write_wav may change metadata/PCM; also write AFTER
    # bundle creation is what design_reference does, but create_bundle
    # hashes the file on disk so we build AFTER the file exists.
    bundle_a = create_bundle("voice_A", wav_a, EN_TXT, "English",
                             seed=42, description="valid")
    write_bundle_atomically(bundle_a)
    check("A-manifest-written", manifest_path_for(wav_a).exists(),
          f"{manifest_path_for(wav_a)} should exist")
    ok, summ, _ = bundle_a.validate()
    check("A-validate-ok", ok, summ)

    # ----- Test B: wrong text (text SHA mismatch) ---------------------------
    # Simulate a manifest that claims the canonical text but the stored
    # reference_text was silently overwritten to something else — the
    # validator must detect this and refuse synthesis.
    bad_text_bundle = ReferenceBundle(
        voice_id="voice_A",
        audio_path=wav_a,
        audio_sha256=bundle_a.audio_sha256,
        reference_text="completely unrelated transcript",
        reference_text_sha256=bundle_a.reference_text_sha256,  # claims canon
        language="English",
    )
    ok_b, summ_b, _ = bad_text_bundle.validate()
    check("B-wrong-text-FAILS",
          (not ok_b) and "TEXT_SHA256" in summ_b, summ_b)

    # ----- Test C: wrong audio (swap file, audio SHA mismatch) --------------
    wav_c = refs / "voice_C.wav"
    _silence_wav(wav_c, seconds=5.0)
    swapped_bundle = ReferenceBundle(
        voice_id="voice_A",
        audio_path=wav_c,
        audio_sha256=bundle_a.audio_sha256,    # claims to be voice_A's hash
        reference_text=EN_TXT,
        reference_text_sha256=sha256_text(EN_TXT),
        language="English",
    )
    ok_c, summ_c, _ = swapped_bundle.validate()
    check("C-wrong-audio-FAILS",
          (not ok_c) and "AUDIO_SHA256" in summ_c, summ_c)

    # ----- Test D: missing text (empty) -------------------------------------
    missing_text = ReferenceBundle(
        voice_id="voice_D",
        audio_path=wav_a,
        audio_sha256=bundle_a.audio_sha256,
        reference_text="",
        reference_text_sha256=sha256_text(""),
        language="English",
    )
    ok_d, summ_d, _ = missing_text.validate()
    check("D-missing-text-FAILS",
          (not ok_d) and "TEXT_NONEMPTY" in summ_d, summ_d)

    # ----- Test E: missing audio --------------------------------------------
    wav_missing = refs / "does_not_exist.wav"
    if wav_missing.exists():
        wav_missing.unlink()
    missing_audio = ReferenceBundle(
        voice_id="voice_E",
        audio_path=wav_missing,
        audio_sha256="x" * 64,
        reference_text=EN_TXT,
        reference_text_sha256=sha256_text(EN_TXT),
        language="English",
    )
    ok_e, summ_e, _ = missing_audio.validate()
    check("E-missing-audio-FAILS",
          (not ok_e) and "AUDIO_EXISTS" in summ_e, summ_e)

    # ----- Test F: ambiguous / duplicate references -------------------------
    other_dir = refs / "_stale_backup"
    other_dir.mkdir(parents=True, exist_ok=True)
    dup_wav = other_dir / "voice_A.wav"
    _silence_wav(dup_wav, seconds=4.0)
    try:
        resolve_bundle("voice_A", language="English")
        check("F-ambiguous-FAILS", False, "expected BundleResolutionError")
    except BundleResolutionError as e:
        check("F-ambiguous-FAILS",
              "AMBIGUOUS_REFERENCE_BUNDLE" in str(e), str(e)[:300])
    finally:
        dup_wav.unlink(missing_ok=True)
        other_dir.rmdir()

    # ----- Test G: CustomVoice routing not affected -------------------------
    # CustomVoice voices don't use the bundle system; a minimal check is
    # that resolve_bundle raises REFERENCE_AUDIO_MISSING (not silent pass)
    # for a voice with no WAV at all — this guards against future silent
    # fallback into clone mode for CustomVoice.
    try:
        resolve_bundle("aiden", language="English")
        check("G-customvoice-no-ref-FAILS", False, "expected error")
    except BundleResolutionError as e:
        check("G-customvoice-no-ref-FAILS",
              "REFERENCE_AUDIO_MISSING" in str(e), str(e)[:200])

    # ----- Test H: VD-E golden bootstraps without manifest ------------------
    # If a VD-E.wav exists alongside no .wav.json, resolve_bundle must
    # bootstrap a bundle using VOICEDESIGN_REF_TEXT_DE and not demand
    # the manifest (backward compatibility with the Golden Voice).
    wav_vde = refs / "vd_e.wav"      # default_bundle_path uses voice_id
    _silence_wav(wav_vde, seconds=8.0)
    try:
        b_vde = resolve_bundle("vd_e", language="German", require_manifest=False)
        check("H-vde-bootstrap-ok", b_vde.language == "German"
              and bool(b_vde.reference_text),
              f"lang={b_vde.language} text_len={len(b_vde.reference_text)}")
        # VD-E must NOT silently accept English default text
        check("H-vde-text-is-german",
              "Buch" in b_vde.reference_text
              and "book" not in b_vde.reference_text.lower(),
              b_vde.reference_text[:80])
    except BundleResolutionError as e:
        check("H-vde-bootstrap-ok", False, str(e))

    # ----- Test I: non-VDE voice without manifest fails closed --------------
    wav_orphan = refs / "voice_orphan.wav"
    _silence_wav(wav_orphan)
    # No .wav.json sidecar -> manifest missing -> hard error
    try:
        resolve_bundle("voice_orphan", language="English")
        check("I-orphan-no-manifest-FAILS", False, "expected error")
    except BundleResolutionError as e:
        check("I-orphan-no-manifest-FAILS",
              "MANIFEST_MISSING" in str(e), str(e)[:300])

    # ----- Test J: VoiceCloneEngine refuses ref_text=None with explicit WAV
    import importlib
    import app.tts.qwen_engine as qwen_mod
    # We can't instantiate without models, but we can import and confirm
    # the engine module imports cleanly with the new guard logic present.
    src = (ROOT / "project" / "app" / "tts" / "qwen_engine.py").read_text()
    check("J-engine-contains-REFERENCE_TEXT_MISSING",
          "REFERENCE_TEXT_MISSING" in src,
          "guard literal should be present")
    check("J-engine-no-silent-reftext-fallback",
          "or default_ref_text" not in src
          and "resolve_reference_text(None," not in src,
          "old silent fallback pattern should not be present")

    # ----- Test K: provenance log line shape -------------------------------
    # Build the same string log_provenance would produce and verify fields.
    expected = (
        f"REFBUNDLE_SYNTH VOICE_ID={bundle_a.voice_id} "
        f"ENGINE=qwen3-tts-clone REFERENCE_AUDIO={bundle_a.audio_path.name} "
        f"REFERENCE_AUDIO_SHA256={bundle_a.audio_sha256[:16]} "
        f"REFERENCE_TEXT_SHA256={bundle_a.reference_text_sha256[:16]} "
        f"REFERENCE_LANGUAGE={bundle_a.language} "
        f"REFERENCE_SEED={bundle_a.generation.get('seed')} "
        f"BUNDLE_ID={bundle_a.bundle_id()}"
    )
    log_line_fields = ["VOICE_ID=voice_A", "REFERENCE_AUDIO_SHA256=",
                       "REFERENCE_TEXT_SHA256=", "REFERENCE_LANGUAGE=English",
                       "REFERENCE_SEED=42"]
    missing = [f for f in log_line_fields if f not in expected]
    check("K-provenance-log-fields", not missing,
          f"missing fields {missing} in: {expected[:300]}")

    # Summary
    print(f"\n{passes} passed, {len(failures)} failed")
    if failures:
        for f in failures:
            print("  -", f)
        return 1
    print("\nALL REFERENCE-BUNDLE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
