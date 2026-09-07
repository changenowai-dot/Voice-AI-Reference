"""Cache-Manager für TTS-Segmente.

Speichert erfolgreich erzeugte Audio-Segmente persistent, damit sie bei
gleichen Eingaben (Text + Stimme + Parameter) nicht neu synthetisiert
werden müssen. Unterstützt Resume über Neustarts hinweg.

Cache-Struktur:
  cache/audio/<key>.wav       – Audio-Daten (WAV)
  cache/metadata/<key>.json   – Metadaten (Score, Text-Preview, Parameter …)

Ein Cache-Eintrag gilt als gültig, wenn sowohl Audio- als auch
Metadaten-Datei existieren und in den Metadaten ``"ok": True`` steht.

Invalidierung:
  Der Cache-Key enthält alle relevanten Parameter (Engine, Modell,
  Speaker, Instruct, Sprache, Text, Sampling-Parameter, Param-Version).
  Ändert sich einer dieser Faktoren, entsteht ein neuer Key → der alte
  Eintrag wird nicht mehr gefunden (effektive Invalidierung).
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

from .. import paths
from ..logging_setup import get_logger

log = get_logger("cache")

# Cache-Version – bei Pipeline-Änderungen hochziehen, damit alte
# Einträge nicht stillschweigend weiterverwendet werden.
CACHE_VERSION = "q3p-v2-integrity"


# =========================================================================
# Cache-Key
# =========================================================================
def segment_cache_key(
    engine: str,
    engine_version: str,
    model_size: str,
    speaker: str,
    instruct: str,
    language: str,
    text: str,
    sampling: dict,
    param_version: str,
) -> str:
    """Erzeugt einen deterministischen SHA-256-Cache-Key aus allen
    relevanten Parametern.

    Änderungen an Engine, Modell, Stimme, Instruct, Sprache, Text oder
    Sampling führen zu einem anderen Key → alte Einträge werden nicht
    mehr gefunden.
    """
    # Sampling als kanonischer JSON-String (sortierte Keys)
    sampling_str = json.dumps(sampling, sort_keys=True, ensure_ascii=False)
    raw = (
        f"{CACHE_VERSION}|"
        f"{engine}|{engine_version}|{model_size}|"
        f"{speaker}|{instruct}|{language}|"
        f"{text}|{sampling_str}|{param_version}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# =========================================================================
# WAV-Helfer (ohne soundfile-Abhängigkeit für minimalen Cache-Betrieb)
# =========================================================================
def _write_wav(path: Path, wav: np.ndarray, sr: int) -> None:
    """Schreibt ein 32-bit-float WAV (PCM-Format)."""
    wav = np.asarray(wav, dtype=np.float32).ravel()
    n_samples = len(wav)
    n_channels = 1
    bits_per_sample = 32
    byte_rate = sr * n_channels * bits_per_sample // 8
    block_align = n_channels * bits_per_sample // 8
    data_size = n_samples * block_align

    path.parent.mkdir(parents=True, exist_ok=True)

    # Atomar: erst tmp, dann rename
    fd, tmp = tempfile.mkstemp(suffix=".wav", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            # RIFF header
            f.write(b"RIFF")
            f.write(struct.pack("<I", 36 + data_size))
            f.write(b"WAVE")
            # fmt chunk
            f.write(b"fmt ")
            f.write(struct.pack("<I", 16))           # chunk size
            f.write(struct.pack("<H", 3))            # IEEE float
            f.write(struct.pack("<H", n_channels))
            f.write(struct.pack("<I", sr))
            f.write(struct.pack("<I", byte_rate))
            f.write(struct.pack("<H", block_align))
            f.write(struct.pack("<H", bits_per_sample))
            # data chunk
            f.write(b"data")
            f.write(struct.pack("<I", data_size))
            f.write(wav.tobytes())
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_wav(path: Path) -> tuple[np.ndarray, int]:
    """Liest ein WAV (float32 oder int16/int24/int32) und gibt
    (waveform_float32, sample_rate) zurück."""
    with open(path, "rb") as f:
        data = f.read()

    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError(f"Keine WAV-Datei: {path}")

    pos = 12
    fmt_sr = None
    fmt_channels = None
    fmt_bits = None
    fmt_code = None
    audio_data = None

    while pos < len(data) - 8:
        chunk_id = data[pos:pos + 4]
        chunk_size = struct.unpack("<I", data[pos + 4:pos + 8])[0]
        pos += 8
        if chunk_id == b"fmt ":
            fmt_code = struct.unpack("<H", data[pos:pos + 2])[0]
            fmt_channels = struct.unpack("<H", data[pos + 2:pos + 4])[0]
            fmt_sr = struct.unpack("<I", data[pos + 4:pos + 8])[0]
            fmt_bits = struct.unpack("<H", data[pos + 14:pos + 16])[0]
        elif chunk_id == b"data":
            audio_data = data[pos:pos + chunk_size]
        pos += chunk_size

    if fmt_sr is None or audio_data is None:
        raise ValueError(f"Unvollständige WAV-Datei: {path}")

    if fmt_code == 3:  # IEEE float
        wav = np.frombuffer(audio_data, dtype=np.float32)
    elif fmt_code == 1:  # PCM int
        if fmt_bits == 16:
            wav = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
        elif fmt_bits == 24:
            # 24-bit PCM -> float32
            n = len(audio_data) // 3
            wav = np.zeros(n, dtype=np.float32)
            for i in range(n):
                b = audio_data[i * 3:(i + 1) * 3]
                val = int.from_bytes(b, "little", signed=True)
                wav[i] = val / 8388608.0
        elif fmt_bits == 32:
            wav = np.frombuffer(audio_data, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            raise ValueError(f"Unsupported PCM bit depth: {fmt_bits}")
    else:
        raise ValueError(f"Unsupported WAV format code: {fmt_code}")

    return wav, fmt_sr


# =========================================================================
# CacheManager
# =========================================================================
class CacheManager:
    """Persistenter Audio-Segment-Cache.

    ``enabled=False`` -> Lese-Modus (Stats anzeigen, aber nichts schreiben).
    ``enabled=True``  -> voller Lese-/Schreibmodus.
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._audio_dir = paths.CACHE_AUDIO_DIR
        self._meta_dir = paths.CACHE_META_DIR
        if enabled:
            self._audio_dir.mkdir(parents=True, exist_ok=True)
            self._meta_dir.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------------------- Pfade
    def _wav_path(self, key: str) -> Path:
        return self._audio_dir / f"{key}.wav"

    def _meta_path(self, key: str) -> Path:
        return self._meta_dir / f"{key}.json"

    # --------------------------------------------------------------- API
    def has(self, key: str) -> bool:
        """True wenn ein gültiger Cache-Eintrag existiert."""
        wav_p = self._wav_path(key)
        meta_p = self._meta_path(key)
        if not (wav_p.exists() and meta_p.exists()):
            return False
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            return bool(meta.get("ok"))
        except (json.JSONDecodeError, OSError):
            return False

    def get(self, key: str) -> tuple[np.ndarray, int, dict] | None:
        """Liest ein gecachtes Segment: (waveform, sample_rate, metadata).
        Gibt None zurück, wenn nicht vorhanden oder ungültig."""
        wav_p = self._wav_path(key)
        meta_p = self._meta_path(key)
        if not (wav_p.exists() and meta_p.exists()):
            return None
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not meta.get("ok"):
            return None
        try:
            wav, sr = _read_wav(wav_p)
            return wav, sr, meta
        except Exception as e:
            log.warning("Cache-Read-Fehler (%s): %s", key[:12], e)
            return None

    def put(self, key: str, wav: np.ndarray, sr: int,
            metadata: dict) -> None:
        """Speichert ein Segment im Cache (atomar)."""
        if not self.enabled:
            return
        wav_p = self._wav_path(key)
        meta_p = self._meta_path(key)
        try:
            _write_wav(wav_p, wav, sr)
            meta_p.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            log.debug("Cache PUT: %s (%.1f s)", key[:12], len(wav) / sr)
        except Exception as e:
            log.error("Cache-Write-Fehler (%s): %s", key[:12], e)
            # Aufräumen bei Schreibfehler
            try:
                wav_p.unlink(missing_ok=True)
                meta_p.unlink(missing_ok=True)
            except OSError:
                pass

    def clear_segment(self, key: str) -> bool:
        """Entfernt einen einzelnen Cache-Eintrag. True wenn gelöscht."""
        removed = False
        for p in (self._wav_path(key), self._meta_path(key)):
            if p.exists():
                try:
                    p.unlink()
                    removed = True
                except OSError:
                    pass
        return removed

    def clear_failed(self) -> int:
        """Entfernt alle Cache-Einträge mit ok=False."""
        removed = 0
        if not self._meta_dir.exists():
            return 0
        for meta_p in self._meta_dir.glob("*.json"):
            try:
                meta = json.loads(meta_p.read_text(encoding="utf-8"))
                if not meta.get("ok"):
                    key = meta_p.stem
                    self.clear_segment(key)
                    removed += 1
            except (json.JSONDecodeError, OSError):
                pass
        return removed

    def clear_project(self, project_id: str) -> int:
        """Entfernt alle Cache-Einträge eines bestimmten Projekts."""
        if not project_id or not self._meta_dir.exists():
            return 0
        removed = 0
        for meta_p in self._meta_dir.glob("*.json"):
            try:
                meta = json.loads(meta_p.read_text(encoding="utf-8"))
                if meta.get("project_id") == project_id:
                    key = meta_p.stem
                    self.clear_segment(key)
                    removed += 1
            except (json.JSONDecodeError, OSError):
                pass
        return removed

    def clear_all(self) -> int:
        """Entfernt alle Cache-Einträge."""
        removed = 0
        for d in (self._audio_dir, self._meta_dir):
            if not d.exists():
                continue
            for f in d.iterdir():
                try:
                    f.unlink()
                    removed += 1
                except OSError:
                    pass
        log.info("Cache CLEAR ALL: %d Dateien entfernt", removed)
        return removed

    def stats(self) -> dict:
        """Statistiken: Anzahl Segmente, Gesamtgröße."""
        n_audio = 0
        n_meta = 0
        size_audio = 0
        size_meta = 0
        if self._audio_dir.exists():
            for f in self._audio_dir.iterdir():
                try:
                    n_audio += 1
                    size_audio += f.stat().st_size
                except OSError:
                    pass
        if self._meta_dir.exists():
            for f in self._meta_dir.iterdir():
                try:
                    n_meta += 1
                    size_meta += f.stat().st_size
                except OSError:
                    pass
        return {
            "segments": min(n_audio, n_meta),
            "audio_files": n_audio,
            "meta_files": n_meta,
            "audio_bytes": size_audio,
            "meta_bytes": size_meta,
            "total_bytes": size_audio + size_meta,
            "enabled": self.enabled,
        }
