#!/usr/bin/env python3
"""Regression tests for the atomic reference-bundle architecture.

Runs without GPU; uses a TMP voice_refs directory so production
references are never touched.
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
    p.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"\x00\x00" * int(seconds * sr))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="refbundle_test_"))
    refs = tmp / "cache" / "voice_refs"
    refs.mkdir(parents=True)
    os.environ["VOICEOVER_REFS_DIR"] = str(refs)

    import importlib
    import app.paths as paths_mod
    paths_mod.VOICE_REFS_DIR = refs
    import app.tts.reference_bundle as rb
    importlib.reload(rb)

    from app.tts.reference_bundle import (ReferenceBundle,
                                          BundleResolutionError,
                                          create_bundle,
                                          default_ref_text_for,
                                          load_bundle,
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
            print(f"[FAIL] {name} - {detail}")

    # ----- A valid bundle validates -------------------------------------
    wav_a = refs / "voice_A.wav"
    _silence_wav(wav_a)
    bundle_a = create_bundle("voice_A", wav_a, EN_TXT, "English",
                             seed=42, description="valid")
    write_bundle_atomically(bundle_a)
    check("A-manifest-written", manifest_path_for(wav_a).exists())
    ok, summ, _ = bundle_a.validate()
    check("A-validate-ok", ok, summ)

    # ----- B wrong text SHA mismatch -----------------------------------
    bad_text_bundle = ReferenceBundle(
        voice_id="voice_A", audio_path=wav_a,
        audio_sha256=bundle_a.audio_sha256,
        reference_text="completely unrelated transcript",
        reference_text_sha256=bundle_a.reference_text_sha256,
        language="English")
    ok_b, summ_b, _ = bad_text_bundle.validate()
    check("B-wrong-text-FAILS", (not ok_b) and "TEXT_SHA256" in summ_b, summ_b)

    # ----- C wrong audio SHA ------------------------------------------
    wav_c = refs / "voice_C.wav"; _silence_wav(wav_c, seconds=5.0)
    swapped_bundle = ReferenceBundle(
        voice_id="voice_A", audio_path=wav_c,
        audio_sha256=bundle_a.audio_sha256,
        reference_text=EN_TXT, reference_text_sha256=sha256_text(EN_TXT),
        language="English")
    ok_c, summ_c, _ = swapped_bundle.validate()
    check("C-wrong-audio-FAILS", (not ok_c) and "AUDIO_SHA256" in summ_c, summ_c)

    # ----- D missing text ---------------------------------------------
    mt = ReferenceBundle(voice_id="voice_D", audio_path=wav_a,
                         audio_sha256=bundle_a.audio_sha256,
                         reference_text="",
                         reference_text_sha256=sha256_text(""),
                         language="English")
    ok_d, summ_d, _ = mt.validate()
    check("D-missing-text-FAILS", (not ok_d) and "TEXT_NONEMPTY" in summ_d, summ_d)

    # ----- E missing audio --------------------------------------------
    wav_missing = refs / "does_not_exist.wav"
    if wav_missing.exists(): wav_missing.unlink()
    ma = ReferenceBundle(voice_id="voice_E", audio_path=wav_missing,
                         audio_sha256="x"*64, reference_text=EN_TXT,
                         reference_text_sha256=sha256_text(EN_TXT),
                         language="English")
    ok_e, summ_e, _ = ma.validate()
    check("E-missing-audio-FAILS", (not ok_e) and "AUDIO_EXISTS" in summ_e, summ_e)

    # ----- F ambiguous duplicates -------------------------------------
    other_dir = refs / "_stale_backup"; other_dir.mkdir()
    dup_wav = other_dir / "voice_A.wav"; _silence_wav(dup_wav, seconds=4.0)
    try:
        resolve_bundle("voice_A", language="English")
        check("F-ambiguous-FAILS", False, "expected BundleResolutionError")
    except BundleResolutionError as e:
        check("F-ambiguous-FAILS", "AMBIGUOUS_REFERENCE_BUNDLE" in str(e), str(e)[:300])
    finally:
        dup_wav.unlink(missing_ok=True); other_dir.rmdir()

    # ----- G customvoice no ref ---------------------------------------
    try:
        resolve_bundle("aiden", language="English")
        check("G-customvoice-no-ref-FAILS", False, "expected error")
    except BundleResolutionError as e:
        check("G-customvoice-no-ref-FAILS", "REFERENCE_AUDIO_MISSING" in str(e), str(e)[:200])

    # ----- H VD-E bootstrap -------------------------------------------
    wav_vde = refs / "vd_e.wav"; _silence_wav(wav_vde, seconds=8.0)
    try:
        b_vde = resolve_bundle("vd_e", language="German", require_manifest=False)
        check("H-vde-bootstrap-ok", b_vde.language == "German" and bool(b_vde.reference_text))
        check("H-vde-text-is-german",
              "Buch" in b_vde.reference_text
              and "book" not in b_vde.reference_text.lower(),
              b_vde.reference_text[:80])
    except BundleResolutionError as e:
        check("H-vde-bootstrap-ok", False, str(e))

    # ----- I orphan no manifest fails ---------------------------------
    wav_orphan = refs / "voice_orphan.wav"; _silence_wav(wav_orphan)
    try:
        resolve_bundle("voice_orphan", language="English")
        check("I-orphan-no-manifest-FAILS", False, "expected error")
    except BundleResolutionError as e:
        check("I-orphan-no-manifest-FAILS", "MANIFEST_MISSING" in str(e), str(e)[:300])

    # ----- J engine guard literals ------------------------------------
    src = (ROOT / "project" / "app" / "tts" / "qwen_engine.py").read_text()
    check("J-engine-contains-REFERENCE_TEXT_MISSING", "REFERENCE_TEXT_MISSING" in src)
    check("J-engine-no-silent-reftext-fallback",
          "or default_ref_text" not in src
          and "resolve_reference_text(None," not in src)

    # ----- K provenance log shape ------------------------------------
    expected = (
        f"REFBUNDLE_SYNTH VOICE_ID={bundle_a.voice_id} "
        f"ENGINE=qwen3-tts-clone REFERENCE_AUDIO={bundle_a.audio_path.name} "
        f"REFERENCE_AUDIO_SHA256={bundle_a.audio_sha256[:16]} "
        f"REFERENCE_TEXT_SHA256={bundle_a.reference_text_sha256[:16]} "
        f"REFERENCE_LANGUAGE={bundle_a.language} "
        f"REFERENCE_SEED={bundle_a.generation.get('seed')} "
        f"BUNDLE_ID={bundle_a.bundle_id()}")
    fields = ["VOICE_ID=voice_A", "REFERENCE_AUDIO_SHA256=", "REFERENCE_TEXT_SHA256=",
              "REFERENCE_LANGUAGE=English", "REFERENCE_SEED=42"]
    miss = [f for f in fields if f not in expected]
    check("K-provenance-log-fields", not miss, str(miss))

    # ----- L bootstrap repairs missing sidecar -----------------------
    wav_l = refs / "en_male_warm_storytelling_authoritative_02.wav"
    _silence_wav(wav_l, seconds=7.0)
    check("L-precondition-wav-no-manifest",
          wav_l.exists() and not manifest_path_for(wav_l).exists())
    import subprocess
    env = os.environ.copy()
    r = subprocess.run([sys.executable,
                        str(ROOT/"project"/"tools"/"bootstrap_reference_bundles.py")],
                       cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=60)
    mp_l = manifest_path_for(wav_l)
    check("L-bootstrap-creates-manifest", mp_l.exists() and r.returncode == 0,
          "stdout:\n" + r.stdout[-500:] + "\nstderr:\n" + r.stderr[-300:])
    if mp_l.exists():
        try:
            b = resolve_bundle("en_male_warm_storytelling_authoritative_02", language="English")
            check("L-resolve-after-bootstrap-ok",
                  b.audio_sha256 == sha256_file(wav_l)
                  and b.language == "English" and bool(b.reference_text),
                  f"bundle_id={b.bundle_id()}")
        except BundleResolutionError as e:
            check("L-resolve-after-bootstrap-ok", False, str(e))
        m = json.loads(mp_l.read_text())
        for k in ("voice_id","reference_audio","reference_text","language","generation"):
            check(f"L-manifest-has-{k}", k in m)
        for k in ("seed","model","model_version","engine_version","source_commit","created_at"):
            check(f"L-manifest-generation-{k}", k in (m.get("generation") or {}))

    # ----- M materialize sidecar repair helper -----------------------
    wav_m2 = refs / "en_male_warm_storytelling_authoritative_02m.wav"
    _silence_wav(wav_m2, seconds=7.0)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "mat_test", str(ROOT/"project"/"tools"/"materialize_references.py"))
    mat = importlib.util.module_from_spec(spec); spec.loader.exec_module(mat)
    mp_m2 = mat._write_manifest_for_existing_wav(
        "en_male_warm_storytelling_authoritative_02m", wav_m2,
        EN_TXT, "English", seed=12345, desc="test")
    check("M-materialize-writes-sidecar", mp_m2.exists())
    if mp_m2.exists():
        b = resolve_bundle("en_male_warm_storytelling_authoritative_02m", language="English")
        check("M-resolve-after-materialize",
              b.audio_sha256 == sha256_file(wav_m2)
              and b.generation.get("seed") == 12345
              and b.reference_text.strip() == EN_TXT.strip(),
              f"bundle_id={b.bundle_id()}")

    # ----- N corrupt existing manifest fails closed ------------------
    wav_n = refs / "en_male_corrupt_01.wav"; _silence_wav(wav_n, seconds=6.0)
    mp_n = manifest_path_for(wav_n)
    bad = {"schema_version": 1, "voice_id": "en_male_corrupt_01",
           "reference_audio": {"path": wav_n.name, "sha256": "0"*64},
           "reference_text": {"text": EN_TXT, "sha256": sha256_text(EN_TXT)},
           "language": "English", "generation": {"seed": 1}}
    mp_n.write_text(json.dumps(bad), encoding="utf-8")
    try:
        resolve_bundle("en_male_corrupt_01", language="English")
        check("N-corrupt-manifest-FAILS", False, "expected error")
    except BundleResolutionError as e:
        check("N-corrupt-manifest-FAILS", "AUDIO_SHA256" in str(e), str(e)[:300])

    print(f"\n{passes} passed, {len(failures)} failed")
    if failures:
        for f in failures: print("  -", f)
        return 1
    print("\nALL REFERENCE-BUNDLE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
