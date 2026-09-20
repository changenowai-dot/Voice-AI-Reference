"""Reference bundle – atomic audio + text provenance for clone voices.

The architecture required by the long-form stability fix: every VoiceDesign
clone voice is represented as ONE immutable bundle that ties together

  * reference WAV path
  * reference WAV sha256
  * literal reference text (the exact transcript spoken in the WAV)
  * reference text sha256
  * language, seed, model/engine/version identifiers, creation timestamp
  * source-commit the bundle was materialized under

rather than two independently selectable values ``reference_path`` and
``ref_text`` that can silently drift apart (the gibberish root cause for
``en_male_warm_storytelling_authoritative_02`` and other premium voices).

Design notes
------------
* The manifest lives as a SIDECAR next to the WAV:
  ``cache/voice_refs/<voice_id>.wav.json``. It is written atomically
  (tmp + rename) directly after the WAV in ``design_reference`` so a
  partial reference (WAV without manifest or vice-versa) is never a
  valid production reference.
* For the Golden Voice (VD-E) the historic ``reference_sha256`` and
  locked ref_text are accepted as canonical even though the WAV was
  created before this manifest scheme existed: see
  :func:`vd_e_bootstrap_bundle`. We DO NOT touch the VD-E WAV.
* Validation runs BEFORE synthesis. A mismatch is a hard failure with a
  human-readable ``REFERENCE_BUNDLE_INVALID`` diagnostic — never a
  silent ``ref_text=None`` fallback.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import wave
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from .. import paths
from ..logging_setup import get_logger

log = get_logger("refbundle")


def _load_default_ref_texts() -> tuple[str, str]:
    """Parse VOICEDESIGN_REF_TEXT_{EN,DE} lazily (avoid numpy/torch chain)."""
    import ast as _ast
    from pathlib import Path as _P
    cache = getattr(_load_default_ref_texts, "_cache", None)
    if cache:
        return cache
    _instruct = _P(__file__).resolve().parents[1] / "prosody" / "instruct.py"
    en = de = ""
    try:
        tree = _ast.parse(_instruct.read_text(encoding="utf-8"))
    except Exception:
        tree = None
    if tree is not None:
        for node in tree.body:
            if isinstance(node, _ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, _ast.Name):
                        if tgt.id == "VOICEDESIGN_REF_TEXT_EN":
                            try: en = _ast.literal_eval(node.value)
                            except Exception: pass
                        elif tgt.id == "VOICEDESIGN_REF_TEXT_DE":
                            try: de = _ast.literal_eval(node.value)
                            except Exception: pass
    _load_default_ref_texts._cache = (en, de)   # type: ignore[attr-defined]
    return en, de

BUNDLE_MANIFEST_SUFFIX = ".wav.json"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class ReferenceBundle:
    """One immutable (audio, text, provenance) tuple for a clone voice."""
    voice_id: str
    audio_path: Path
    audio_sha256: str
    reference_text: str
    reference_text_sha256: str
    language: str
    generation: dict[str, Any] = field(default_factory=dict)

    # -- validation ------------------------------------------------------
    def validate(self, *, wav_must_exist: bool = True) -> tuple[bool, str, dict]:
        """Validate bundle integrity. Returns (ok, human_summary, detail)."""
        diag: dict[str, Any] = {
            "voice_id": self.voice_id,
            "audio_path": str(self.audio_path),
            "audio_sha256_expected": self.audio_sha256,
            "text_sha256_expected": self.reference_text_sha256,
            "language": self.language,
        }
        checks: list[tuple[str, bool, str]] = []

        # 1. WAV exists & readable
        exists = self.audio_path.exists()
        checks.append(("AUDIO_EXISTS", exists,
                       f"{'found' if exists else 'MISSING'}: {self.audio_path}"))
        if not exists and wav_must_exist:
            return _summarize(False, "REFERENCE_AUDIO_MISSING", diag, checks)

        if exists:
            # 2. Readable WAV header
            try:
                with wave.open(str(self.audio_path), "rb") as w:
                    nframes = w.getnframes()
                    sr = w.getframerate()
                    ch = w.getnchannels()
                    sw = w.getsampwidth()
                wav_ok = nframes > 0 and sr in (16000, 22050, 24000, 44100, 48000)
                dur_s = nframes / float(max(1, sr))
                diag.update({"sample_rate": sr, "channels": ch,
                             "sample_width_bytes": sw, "duration_s": round(dur_s, 3)})
                checks.append(("AUDIO_READABLE", wav_ok,
                               f"sr={sr} ch={ch} dur={dur_s:.2f}s"))
            except Exception as e:                    # noqa: BLE001
                checks.append(("AUDIO_READABLE", False, f"wave open failed: {e}"))
                return _summarize(False, "REFERENCE_AUDIO_UNREADABLE", diag, checks)

            # 3. Duration bounds (VoiceDesign references are ~6–15 s).
            dur_ok = 2.0 <= dur_s <= 60.0
            checks.append(("AUDIO_DURATION_RANGE", dur_ok,
                           f"duration_s={dur_s:.2f} expected in [2,60]"))

            # 4. Audio sha256 matches manifest
            actual_sha = sha256_file(self.audio_path)
            sha_ok = (actual_sha.lower() == self.audio_sha256.lower()) if self.audio_sha256 else False
            diag["audio_sha256_actual"] = actual_sha
            checks.append(("AUDIO_SHA256", sha_ok,
                           f"expected={self.audio_sha256[:16]}… actual={actual_sha[:16]}…"))
            if not sha_ok:
                return _summarize(False, "REFERENCE_AUDIO_HASH_MISMATCH", diag, checks)

        # 5. Reference text non-empty
        text_ok = bool(self.reference_text and self.reference_text.strip())
        checks.append(("TEXT_NONEMPTY", text_ok,
                       f"len={len(self.reference_text) if self.reference_text else 0}"))
        if not text_ok:
            return _summarize(False, "REFERENCE_TEXT_MISSING", diag, checks)

        # 6. Reference text sha256 matches manifest
        actual_text_sha = sha256_text(self.reference_text)
        tsha_ok = actual_text_sha.lower() == self.reference_text_sha256.lower()
        diag["text_sha256_actual"] = actual_text_sha
        checks.append(("TEXT_SHA256", tsha_ok,
                       f"expected={self.reference_text_sha256[:16]}… actual={actual_text_sha[:16]}…"))
        if not tsha_ok:
            return _summarize(False, "REFERENCE_TEXT_HASH_MISMATCH", diag, checks)

        # 7. Language valid
        lang_ok = self.language in ("English", "German")
        checks.append(("LANGUAGE", lang_ok, f"language={self.language}"))
        if not lang_ok:
            return _summarize(False, "REFERENCE_LANGUAGE_INVALID", diag, checks)

        return _summarize(True, "REFERENCE_BUNDLE_VALID", diag, checks)

    def log_provenance(self, prefix: str = "REFBUNDLE") -> None:
        """Emit a single-line provenance record suitable for log grep."""
        log.info(
            "%s VOICE_ID=%s ENGINE=qwen3-tts-clone "
            "REFERENCE_AUDIO=%s REFERENCE_AUDIO_SHA256=%s "
            "REFERENCE_TEXT_SHA256=%s REFERENCE_LANGUAGE=%s "
            "REFERENCE_SEED=%s BUNDLE_ID=%s",
            prefix, self.voice_id,
            self.audio_path.name, self.audio_sha256[:16],
            self.reference_text_sha256[:16], self.language,
            self.generation.get("seed"), self.bundle_id())

    def bundle_id(self) -> str:
        return f"{self.voice_id}:{self.audio_sha256[:12]}"

    def to_manifest_dict(self) -> dict:
        return {
            "schema_version": 1,
            "voice_id": self.voice_id,
            "reference_audio": {
                "path": str(self.audio_path.name),  # relative to VOICE_REFS_DIR
                "sha256": self.audio_sha256,
            },
            "reference_text": {
                "text": self.reference_text,
                "sha256": self.reference_text_sha256,
            },
            "language": self.language,
            "generation": self.generation,
        }


def _summarize(ok: bool, code: str, diag: dict,
               checks: list[tuple[str, bool, str]]) -> tuple[bool, str, dict]:
    detail = dict(diag)
    detail["checks"] = [{"name": n, "passed": p, "detail": d} for (n, p, d) in checks]
    detail["code"] = code
    lines = [f"{code} VOICE={diag.get('voice_id','?')}"]
    for n, p, d in checks:
        lines.append(f"  [{'PASS' if p else 'FAIL'}] {n}: {d}")
    return ok, ("\n".join(lines)), detail


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------
def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _source_commit() -> str | None:
    try:
        import subprocess
        r = subprocess.run(["git", "rev-parse", "HEAD"],
                           cwd=str(paths.ROOT), capture_output=True,
                           timeout=5, check=False)
        if r.returncode == 0:
            return r.stdout.decode("utf-8", errors="replace").strip()
    except Exception:                                   # noqa: BLE001
        pass
    return None


# ---------------------------------------------------------------------------
# Bundle I/O
# ---------------------------------------------------------------------------
def manifest_path_for(wav_path: Path) -> Path:
    """Return the canonical sidecar path for a WAV's manifest."""
    return wav_path.with_name(wav_path.name + ".json")


def default_bundle_path(voice_id: str) -> Path:
    """Preferred runtime (cache) location for a voice's reference WAV."""
    return paths.VOICE_REFS_DIR / f"{voice_id}.wav"


def bundled_bundle_path(voice_id: str) -> Path:
    """Release-bundled (immutable) reference WAV shipped with the repo."""
    return paths.BUNDLED_REF_DIR / f"{voice_id}.wav"


# ---------------------------------------------------------------------------
# Auto-materialization: populate VOICE_REFS_DIR from bundled/Golden sources
# on first run (idempotent, never overwrites an existing cache entry).
# ---------------------------------------------------------------------------
_materialized: set[str] = set()   # process-local memo; avoids re-copy per call


def _materialize_vd_e_from_golden() -> Path | None:
    """Copy the locked Golden VD-E into the runtime cache if missing.

    Returns the resulting cache path, or None if the Golden reference is
    not available at all (caller surfaces that as a hard error).

    The Golden WAV itself is NEVER modified; we only copy and verify SHA.
    """
    cache_wav = default_bundle_path("vd_e")
    if cache_wav.exists():
        return cache_wav
    golden = paths.VD_E_GOLDEN_REF_PATH
    if not golden.exists():
        # legacy top-level location
        legacy = paths.ROOT.parent / "reference" / "VD-E_GOLDEN_REFERENCE" / "VD-E.wav"
        if legacy.exists():
            golden = legacy
        else:
            return None
    import shutil
    cache_wav.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(golden, cache_wav)
    # Verify SHA after copy — corruption defense.
    actual = sha256_file(cache_wav)
    if actual.lower() != paths.VD_E_EXPECTED_SHA256.lower():
        try:
            cache_wav.unlink()
        except Exception:                               # noqa: BLE001
            pass
        raise BundleResolutionError(
            "VD_E_GOLDEN_SHA_MISMATCH\n"
            f"Golden source: {golden}\n"
            f"Copied to:     {cache_wav}\n"
            f"Expected SHA:  {paths.VD_E_EXPECTED_SHA256}\n"
            f"Actual SHA:    {actual}\n"
            "Identity lock FAILED; refusing to proceed. Re-acquire the "
            "untouched Golden Reference VD-E.wav.")
    return cache_wav


def _materialize_from_bundled(voice_id: str) -> Path | None:
    """Copy a bundle shipped with the release into the runtime cache.

    Copies both the WAV and the sidecar manifest (if present). Returns the
    cache WAV path, or None if no bundled copy exists. Never overwrites
    an existing cache entry (user materialization wins).
    """
    cache_wav = default_bundle_path(voice_id)
    if cache_wav.exists():
        return cache_wav
    src_wav = bundled_bundle_path(voice_id)
    if not src_wav.exists():
        return None
    import shutil
    cache_wav.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_wav, cache_wav)
    src_manifest = manifest_path_for(src_wav)
    dst_manifest = manifest_path_for(cache_wav)
    if src_manifest.exists() and not dst_manifest.exists():
        shutil.copy2(src_manifest, dst_manifest)
    return cache_wav


def ensure_bundle_materialized(voice_id: str) -> Path | None:
    """Best-effort materialization. Returns resolved cache WAV or None."""
    if voice_id in _materialized:
        return default_bundle_path(voice_id)
    # Priority order: cache > bundled > (VD-E golden special case)
    if voice_id == "vd_e":
        result = _materialize_vd_e_from_golden()
    else:
        result = _materialize_from_bundled(voice_id)
    if result is not None:
        _materialized.add(voice_id)
    return result


def write_bundle_atomically(bundle: ReferenceBundle) -> Path:
    """Write bundle manifest next to its WAV with tmp+rename.

    The WAV itself is assumed to already exist (written by
    ``write_wav`` in ``design_reference``) and is not rewritten.
    """
    bundle.audio_path.parent.mkdir(parents=True, exist_ok=True)
    mp = manifest_path_for(bundle.audio_path)
    payload = json.dumps(bundle.to_manifest_dict(), indent=2, ensure_ascii=False)
    fd, tmp = tempfile.mkstemp(prefix=".bundle_", suffix=".json",
                               dir=str(bundle.audio_path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp, mp)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:                               # noqa: BLE001
            pass
        raise
    return mp


def load_bundle(wav_path: Path, *, voice_id: str | None = None,
                expected_language: str | None = None) -> ReferenceBundle | None:
    """Load bundle from its sidecar. Returns None if manifest missing.

    Does NOT validate — caller should invoke ``bundle.validate()``.
    """
    mp = manifest_path_for(wav_path)
    if not mp.exists():
        return None
    try:
        data = json.loads(mp.read_text(encoding="utf-8"))
    except Exception:                                   # noqa: BLE001
        return None
    if not isinstance(data, dict):
        return None
    ra = data.get("reference_audio") or {}
    rt = data.get("reference_text") or {}
    vid = data.get("voice_id") or voice_id or wav_path.stem
    rel_audio = ra.get("path") or wav_path.name
    audio_path = wav_path.parent / rel_audio
    text = rt.get("text") or ""
    bundle = ReferenceBundle(
        voice_id=vid,
        audio_path=audio_path,
        audio_sha256=ra.get("sha256") or "",
        reference_text=text,
        reference_text_sha256=rt.get("sha256") or sha256_text(text),
        language=data.get("language") or expected_language or "German",
        generation=dict(data.get("generation") or {}),
    )
    return bundle


def create_bundle(voice_id: str, wav_path: Path, ref_text: str,
                  language: str, *, seed: int | None = None,
                  model: str = "Qwen3-TTS-12Hz-1.7B-VoiceDesign",
                  model_version: str = "unknown",
                  engine_version: str = "qwen-voicestudio-v1",
                  description: str = "",
                  extra: dict | None = None) -> ReferenceBundle:
    """Build a fresh bundle for a just-materialized WAV."""
    audio_sha = sha256_file(wav_path)
    text_sha = sha256_text(ref_text)
    gen = {
        "seed": int(seed) if seed is not None else None,
        "model": model,
        "model_version": model_version,
        "engine_version": engine_version,
        "source_commit": _source_commit(),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "description": description,
    }
    if extra:
        gen.update(extra)
    return ReferenceBundle(
        voice_id=voice_id,
        audio_path=wav_path,
        audio_sha256=audio_sha,
        reference_text=ref_text,
        reference_text_sha256=text_sha,
        language=language,
        generation=gen,
    )


# ---------------------------------------------------------------------------
# Resolution: single canonical bundle per voice_id, no guessing.
# ---------------------------------------------------------------------------
class BundleResolutionError(RuntimeError):
    """Raised when a reference bundle cannot be unambiguously resolved."""


def resolve_bundle(voice_id: str, *, language: str | None = None,
                   require_manifest: bool = False,
                   auto_materialize: bool = True,
                   ) -> ReferenceBundle:
    """Resolve the single canonical reference bundle for ``voice_id``.

    Resolution priority (distribution-first, per release-architecture):
      0. VD-E special: bootstrap from the locked Golden Reference into
         the runtime cache, SHA-verified, then resolve from cache.
      1. **Bundled reference** (immutable, shipped with release, in
         ``project/app/voices/bundles/``) – Source of Truth for
         distribution. If it exists and is valid and auto_materialize
         is True, it is copied idempotently into the runtime cache and
         the cache copy is returned (TTS engine needs a stable writable
         location for converted-cached sidecars).
      2. **Runtime cache** (``project/cache/voice_refs/``) – locally
         materialized/user-generated references; wins over bundled if
         its SHA differs (user-local override / development).
      3. If neither location provides a valid bundle AND
         ``require_manifest`` is False AND ``voice_id == "vd_e"``, the
         implicit Golden bootstrap bundle is used (legacy path for
         VD-E which predates the manifest scheme).
      4. The returned bundle is validated; invalid bundles raise
         :class:`BundleResolutionError` with a human-readable reason.

    Setting ``auto_materialize=False`` makes the function a pure lookup
    (used for availability checks from the GUI without writing to
    cache).
    """
    # --- Lookup both locations without writing ---
    bundled_wav = bundled_bundle_path(voice_id)
    cache_wav = default_bundle_path(voice_id)
    bundled_bundle: ReferenceBundle | None = None
    cache_bundle: ReferenceBundle | None = None

    # Duplicate/ambiguity scan runs over both directories combined.
    candidates = _find_candidate_wavs(voice_id)
    # Strict: any WAV outside the two canonical paths is ambiguous.
    canonical_set = {bundled_wav.resolve(), cache_wav.resolve()}
    non_canon = [c for c in candidates if c.resolve() not in canonical_set]
    if non_canon:
        raise BundleResolutionError(
            "AMBIGUOUS_REFERENCE_BUNDLE VOICE={}\n"
            "Found reference WAV(s) outside the two canonical locations:\n{}\n"
            "Canonical locations:\n  bundled: {}\n  cache:   {}\n"
            "Remove or archive stale duplicates before synthesis; the "
            "system will not guess."
            .format(voice_id, "\n".join(f"  - {c}" for c in non_canon),
                    bundled_wav, cache_wav))

    # Try loading from each location.
    if bundled_wav.exists():
        b = load_bundle(bundled_wav, voice_id=voice_id,
                        expected_language=language)
        if b is not None:
            ok_b, _, _ = b.validate(wav_must_exist=True)
            if ok_b:
                bundled_bundle = b
    if cache_wav.exists():
        c = load_bundle(cache_wav, voice_id=voice_id,
                        expected_language=language)
        if c is not None:
            ok_c, _, _ = c.validate(wav_must_exist=True)
            if ok_c:
                cache_bundle = c

    chosen: ReferenceBundle | None = None
    chosen_location = ""

    if cache_bundle is not None and bundled_bundle is not None:
        if cache_bundle.audio_sha256.lower() == bundled_bundle.audio_sha256.lower():
            # Cache matches bundled → use cache (already materialized).
            chosen, chosen_location = cache_bundle, "cache(=bundled)"
        else:
            # Cache has a different SHA than bundled — treat as a
            # legitimate local override (user-materialized dev copy)
            # but log a warning. Use cache.
            log.warning(
                "REFERENCE_OVERRIDE VOICE=%s: cache SHA %s… differs from "
                "bundled SHA %s… — using cache (local override).",
                voice_id, cache_bundle.audio_sha256[:12],
                bundled_bundle.audio_sha256[:12])
            chosen, chosen_location = cache_bundle, "cache(override)"
    elif cache_bundle is not None:
        chosen, chosen_location = cache_bundle, "cache"
    elif bundled_bundle is not None:
        chosen, chosen_location = bundled_bundle, "bundled"

    # VD-E Golden bootstrap if neither location has anything and VD-E
    # Golden reference is present.
    if chosen is None and voice_id == "vd_e" and not require_manifest:
        if auto_materialize:
            mat = _materialize_vd_e_from_golden()
            if mat is not None and mat.exists():
                after = load_bundle(mat, voice_id="vd_e",
                                    expected_language="German")
                if after is None:
                    # Build implicit bundle (pre-manifest legacy path).
                    _en_default, ref_text = _load_default_ref_texts()
                    chosen = ReferenceBundle(
                        voice_id="vd_e",
                        audio_path=mat,
                        audio_sha256=sha256_file(mat),
                        reference_text=ref_text,
                        reference_text_sha256=sha256_text(ref_text),
                        language="German",
                        generation={"seed": 52001,
                                    "model": "Qwen3-TTS-12Hz-1.7B-VoiceDesign",
                                    "note": "bootstrapped-from-golden"},
                    )
                    chosen_location = "golden(implicit)"
                else:
                    chosen, chosen_location = after, "golden(materialized)"
        else:
            # Lookup-only mode: check if Golden file exists; report it
            # via a synthetic bundle without copying.
            g = paths.VD_E_GOLDEN_REF_PATH
            if g.exists():
                actual_sha = sha256_file(g)
                if actual_sha.lower() != paths.VD_E_EXPECTED_SHA256.lower():
                    raise BundleResolutionError(
                        "VD_E_GOLDEN_SHA_MISMATCH\n"
                        f"File: {g}\nExpected: {paths.VD_E_EXPECTED_SHA256}\n"
                        f"Actual:   {actual_sha}")
                _en_default, ref_text = _load_default_ref_texts()
                chosen = ReferenceBundle(
                    voice_id="vd_e",
                    audio_path=g,
                    audio_sha256=actual_sha,
                    reference_text=ref_text,
                    reference_text_sha256=sha256_text(ref_text),
                    language="German",
                    generation={"note": "golden-readonly-lookup"},
                )
                chosen_location = "golden(readonly)"

    if chosen is None:
        # Not found anywhere — build helpful error.
        hint = (f"REFERENCE_AUDIO_MISSING VOICE={voice_id}\n"
                f"Geprüft:\n"
                f"  (bundled) {bundled_wav}  exists={bundled_wav.exists()}\n"
                f"  (cache)   {cache_wav}    exists={cache_wav.exists()}")
        if voice_id == "vd_e":
            hint += (f"\n  (golden)  {paths.VD_E_GOLDEN_REF_PATH}  "
                     f"exists={paths.VD_E_GOLDEN_REF_PATH.exists()}\n"
                     f"Erwarteter SHA: {paths.VD_E_EXPECTED_SHA256[:16]}…")
        else:
            hint += ("\nDieses Bundle ist nicht Teil des Releases. "
                     "Materialisiere die Stimme auf dem GPU-Host via\n"
                     "  python project/tools/materialize_references.py "
                     f"--voice-id {voice_id}\n"
                     "und importiere sie danach mit\n"
                     "  python project/tools/import_voice_bundles.py "
                     "--from-cache")
        raise BundleResolutionError(hint)

    # If caller knows the language, ensure it matches (non-fatal warning).
    if language and chosen.language != language:
        log.warning("Reference bundle language=%s but requested language=%s "
                    "for %s (location=%s)",
                    chosen.language, language, voice_id, chosen_location)

    # If we resolved the bundle from the bundled folder and caller wants
    # a writable copy (auto_materialize=True), materialize into cache
    # and return the cache copy so downstream engine sees a stable path
    # it can write sidecars to.
    if auto_materialize and chosen_location.startswith("bundled"):
        mat = _materialize_from_bundled(voice_id)
        if mat is not None:
            reloaded = load_bundle(mat, voice_id=voice_id,
                                   expected_language=language)
            if reloaded is not None:
                ok_r, _, _ = reloaded.validate()
                if ok_r:
                    chosen = reloaded
                    chosen_location = "cache(materialized-from-bundled)"

    ok, summary, _detail = chosen.validate()
    if not ok:
        raise BundleResolutionError(
            f"REFERENCE_BUNDLE_INVALID location={chosen_location}\n{summary}")

    chosen.log_provenance(prefix=f"REFBUNDLE[{chosen_location}]")
    return chosen


def _find_candidate_wavs(voice_id: str) -> list[Path]:
    """Find any WAV with the given voice_id stem under either ref dir."""
    out: list[Path] = []
    for d in (paths.VOICE_REFS_DIR, paths.BUNDLED_REF_DIR):
        if not d.exists():
            continue
        for ext in ("wav", "mp3", "flac", "ogg"):
            for p in d.rglob(f"{voice_id}.{ext}"):
                out.append(p)
    return sorted(set(out))


def bundle_exists(voice_id: str, *, language: str | None = None) -> tuple[bool, str]:
    """Pure-existence check (no cache writes). Used by GUI availability.

    Returns (available, human_reason_or_location).
    """
    try:
        b = resolve_bundle(voice_id, language=language,
                           require_manifest=(voice_id != "vd_e"),
                           auto_materialize=False)
        return True, f"bundled/cache: {b.audio_path}"
    except BundleResolutionError as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Convenience: which canonical ref text does a language use?
# ---------------------------------------------------------------------------
def default_ref_text_for(language: str) -> str:
    en, de = _load_default_ref_texts()
    return en if language == "English" else de
