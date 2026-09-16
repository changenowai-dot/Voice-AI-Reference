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
    return paths.VOICE_REFS_DIR / f"{voice_id}.wav"


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
                   require_manifest: bool = False
                   ) -> ReferenceBundle:
    """Resolve the single canonical reference bundle for ``voice_id``.

    Resolution rules (deliberately strict):
      1. The bundle MUST live in ``paths.VOICE_REFS_DIR / f"{voice_id}.wav"``.
      2. If multiple candidate WAVs with the same voice_id stem exist in
         other cache/backup/temp locations that is an
         ``AMBIGUOUS_REFERENCE_BUNDLE`` error.
      3. If a sidecar manifest exists it is loaded and its hashes/language
         validated against the WAV on disk.
      4. If no manifest exists AND ``require_manifest`` is False the bundle
         is constructed ad-hoc for Golden-Voice bootstrapping (VD-E) and
         ONLY if ``voice_id == "vd_e"`` — every other voice without a
         manifest is INVALID (fail closed).
      5. The returned bundle is validated; invalid bundles raise
         :class:`BundleResolutionError` with a human-readable reason.
    """
    ref_dir = paths.VOICE_REFS_DIR
    canonical_wav = ref_dir / f"{voice_id}.wav"

    # 2. Reject duplicate/ambiguous candidates anywhere under cache/voice_refs
    candidates = []
    if ref_dir.exists():
        for ext in ("wav", "mp3", "flac", "ogg"):
            for p in ref_dir.rglob(f"{voice_id}.{ext}"):
                candidates.append(p)
        # also include stem-matches in _converted/ etc.
        for p in ref_dir.rglob(f"{voice_id}*.*"):
            if p.suffix.lower() in (".wav", ".json") or "_converted" in str(p):
                if p not in candidates and p.suffix.lower() == ".wav":
                    candidates.append(p)
    # de-duplicate
    candidates = sorted(set(candidates))
    if len(candidates) > 1:
        # Canonical path is the only accepted one; anything else is ambiguous.
        non_canon = [c for c in candidates if c.resolve() != canonical_wav.resolve()]
        if non_canon:
            raise BundleResolutionError(
                "AMBIGUOUS_REFERENCE_BUNDLE VOICE={}\n"
                "Found multiple candidate reference files for this voice:\n"
                "{}\n"
                "Canonical path expected: {}\n"
                "Remove or archive stale/duplicate files before synthesis; "
                "the system will not guess which one is correct."
                .format(voice_id,
                        "\n".join(f"  - {c}" for c in candidates),
                        canonical_wav))

    if not canonical_wav.exists():
        # CustomVoice voices don't have refs; caller should not ask.
        raise BundleResolutionError(
            f"REFERENCE_AUDIO_MISSING VOICE={voice_id}\n"
            f"Expected canonical reference WAV: {canonical_wav}\n"
            "Materialize it via `python project/tools/materialize_references.py "
            f"--voice-id {voice_id}` on the GPU host, then re-run.")

    # Load manifest sidecar if present
    bundle = load_bundle(canonical_wav, voice_id=voice_id,
                         expected_language=language)

    if bundle is None:
        if voice_id == "vd_e" and not require_manifest:
            # Bootstrap: Golden voice existed before the manifest scheme.
            # Build an implicit bundle from the canonical German ref text.
            _en_default, ref_text = _load_default_ref_texts()
            bundle = ReferenceBundle(
                voice_id="vd_e",
                audio_path=canonical_wav,
                audio_sha256=sha256_file(canonical_wav),
                reference_text=ref_text,
                reference_text_sha256=sha256_text(ref_text),
                language="German",
                generation={"seed": 52001,
                            "model": "Qwen3-TTS-12Hz-1.7B-VoiceDesign",
                            "engine_version": "qwen-voicestudio-v1",
                            "source_commit": _source_commit(),
                            "created_at": "bootstrapped-from-golden",
                            "note": "Golden VD-E; manifest auto-generated at runtime."},
            )
        else:
            raise BundleResolutionError(
                f"REFERENCE_BUNDLE_MANIFEST_MISSING VOICE={voice_id}\n"
                f"Canonical WAV exists at {canonical_wav} but no sidecar "
                f"manifest `{canonical_wav.name}.json` was found.\n"
                "Without a manifest the audio/text provenance cannot be "
                "verified; refuse to synthesize. Re-materialize this voice "
                "via tools/materialize_references.py to write the bundle.")

    # If caller knows the language, ensure it matches.
    if language and bundle.language != language:
        # Not fatal — engine can proceed with bundle language — but log.
        log.warning("Reference bundle language=%s but requested language=%s "
                    "for %s", bundle.language, language, voice_id)

    ok, summary, _detail = bundle.validate()
    if not ok:
        raise BundleResolutionError(summary)

    return bundle


# ---------------------------------------------------------------------------
# Convenience: which canonical ref text does a language use?
# ---------------------------------------------------------------------------
def default_ref_text_for(language: str) -> str:
    en, de = _load_default_ref_texts()
    return en if language == "English" else de
