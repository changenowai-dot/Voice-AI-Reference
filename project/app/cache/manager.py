"""Segment-Audio-Cache (persistente Wiederverwendung bereits synthetisierter
Segmente über Job-Läufe hinweg, §19).

Der Cache speichert pro Segment-Key ein WAV-Numpy-Array + Sampling-Rate +
Meta-Informationen (QC-Score, Issues, Metriken …) als ``.npz`` in
``cache/segments/``. Er wird vom Pipeline-Prozess benutzt, um bereits
erfolgreich erzeugte Segmente nicht nochmals zu synthetisieren (Resume).

ÖFFENTLICHE API:

- ``CacheManager(enabled=bool)`` erstellt einen Cache-Zugriff.
- ``cache.has(key)`` / ``cache.get(key)`` / ``cache.put(key, wav, sr, meta)``
- ``cache.stats()`` / ``cache.clear_all()`` / ``cache.clear_failed()`` /
  ``cache.clear_project(project_id)`` (für die Web-API).
- ``segment_cache_key(**fields)`` erzeugt einen stabilen hex-Key aus den
  Parameterfeldern, die ein Segment determinieren (Text, Stimme,
  Sampling-Parameter, Sprache, Prompt, Modell-Version, …).

Der Cache ist tolerant gegenüber korrupten Einträgen und fehlendem
Speicherplatz (``get`` gibt dann ``None`` zurück, der Synthesepfad
springt ein).
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np

from .. import paths
from ..logging_setup import get_logger

log = get_logger("cache")

# Metadaten-Datei-Version. Bei inkompatiblen Änderungen bumpen – alte
# Einträge werden dann sauber als "veraltet" ignoriert.
CACHE_VERSION = 2


# ---------------------------------------------------------------------------
def _key_to_filename(key: str) -> str:
    """Sichere Schlüssel -> Dateiname (keine `/`, `:`, etc. im Pfad)."""
    safe = key.replace("/", "_").replace("\\", "_").replace(":", "_")
    # Wenn der Key bereits ein Hex-Hash ist, direkt benutzen; sonst hashen
    if len(safe) == 64 and all(c in "0123456789abcdef" for c in safe):
        return safe
    return sha256(safe.encode("utf-8")).hexdigest()


def segment_cache_key(*, engine: str, engine_version: str, model_size: str,
                      speaker: str, instruct: str, language: str,
                      text: str, sampling: dict, param_version: int) -> str:
    """Erzeugt einen stabilen Cache-Schlüssel für ein Segment.

    Zwei Segmente bekommen den gleichen Key genau dann, wenn alle
    Parameter übereinstimmen, die die Audio-Ausgabe determinieren.
    """
    payload = {
        "v": CACHE_VERSION,
        "p": param_version,
        "e": engine,
        "ev": engine_version,
        "ms": model_size,
        "sp": speaker,
        "ins": instruct,
        "lg": language,
        "tx": text,
        "sm": {k: sampling[k] for k in sorted(sampling.keys())}
              if isinstance(sampling, dict) else sampling,
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class _CacheEntry:
    wav: np.ndarray
    sr: int
    meta: dict


class CacheManager:
    """Persistenter NPZ-Cache für synthetisierte Segment-Audiodateien."""

    def __init__(self, enabled: bool = True,
                 cache_dir: Path | None = None):
        self.enabled = bool(enabled)
        self.dir = Path(cache_dir) if cache_dir else paths.CACHE_SEGMENT_DIR
        if self.enabled:
            try:
                self.dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                log.warning("Segment-Cache-Verzeichnis nicht anlegbar "
                            "(%s) – Cache deaktiviert.", e)
                self.enabled = False

    # ---------------------------------------------------------------- Pfad
    def _path(self, key: str) -> Path:
        return self.dir / f"{_key_to_filename(key)}.npz"

    # ---------------------------------------------------------------- has
    def has(self, key: str) -> bool:
        if not self.enabled:
            return False
        try:
            return self._path(key).is_file()
        except OSError:
            return False

    # ---------------------------------------------------------------- get
    def get(self, key: str) -> tuple[np.ndarray, int, dict] | None:
        if not self.enabled:
            return None
        p = self._path(key)
        if not p.is_file():
            return None
        try:
            with np.load(p, allow_pickle=False) as z:
                if z.get("cache_version", 0) != CACHE_VERSION:
                    return None
                wav = z["wav"]
                sr = int(z["sr"])
                meta = json.loads(z["meta"].item().decode("utf-8")) \
                    if "meta" in z.files else {}
                if wav.size == 0 or sr <= 0:
                    return None
                return wav, sr, meta
        except Exception as e:                              # noqa: BLE001
            log.debug("Cache-Eintrag unlesbar %s: %s", key, e)
            # Defekt -> still ignorieren (wird neu erzeugt)
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
            return None

    # ---------------------------------------------------------------- put
    def put(self, key: str, wav: np.ndarray, sr: int, meta: dict | None = None
            ) -> bool:
        if not self.enabled:
            return False
        try:
            p = self._path(key)
            p.parent.mkdir(parents=True, exist_ok=True)
            meta_clean: dict[str, Any] = {}
            if meta:
                # Nur JSON-serialisierbare Werte übernehmen; numpy-Typen
                # nach float/int/cast, um np.savez nicht mit Objekten zu
                # belasten.
                for k, v in meta.items():
                    try:
                        json.dumps(v)
                        meta_clean[k] = v
                    except TypeError:
                        try:
                            meta_clean[k] = float(v)
                        except Exception:                              # noqa: BLE001
                            meta_clean[k] = str(v)
            tmp = p.with_suffix(".tmp.npz")
            np.savez(tmp,
                     wav=wav, sr=np.int64(sr),
                     cache_version=np.int64(CACHE_VERSION),
                     meta=np.array(
                         json.dumps(meta_clean,
                                    ensure_ascii=False).encode("utf-8")))
            os.replace(tmp, p)
            return True
        except Exception as e:                                  # noqa: BLE001
            log.warning("Cache-Schreiben fehlgeschlagen für %s: %s", key, e)
            try:
                if tmp.exists():                                   # type: ignore[name-defined]
                    tmp.unlink(missing_ok=True)
            except Exception:                                      # noqa: BLE001
                pass
            return False

    # ---------------------------------------------------------------- stats
    def stats(self) -> dict:
        """Statistik für UI / API (Anzahl Einträge, Größe)."""
        out = {"enabled": self.enabled,
               "dir": str(self.dir),
               "entries": 0, "bytes": 0,
               "failed_entries": 0,
               "version": CACHE_VERSION}
        if not self.enabled:
            return out
        try:
            for p in self.dir.glob("*.npz"):
                try:
                    st = p.stat()
                    out["entries"] += 1
                    out["bytes"] += st.st_size
                except OSError:
                    pass
        except OSError:
            pass
        return out

    # --------------------------------------------------------------- clear
    def clear_all(self) -> int:
        n = 0
        if not self.enabled:
            return 0
        for p in list(self.dir.glob("*.npz")):
            try:
                p.unlink()
                n += 1
            except OSError:
                pass
        log.info("Cache geleert: %d Einträge entfernt", n)
        return n

    def clear_failed(self) -> int:
        """Einträge ohne gültiges WAV oder mit ok=False/fehlendem Score
        entfernen."""
        n = 0
        if not self.enabled:
            return 0
        for p in list(self.dir.glob("*.npz")):
            remove = False
            try:
                with np.load(p, allow_pickle=False) as z:
                    if z.get("cache_version", 0) != CACHE_VERSION:
                        remove = True
                    elif "wav" not in z.files or z["wav"].size == 0:
                        remove = True
                    elif "meta" in z.files:
                        m = json.loads(z["meta"].item().decode("utf-8"))
                        if m.get("ok") is False:
                            remove = True
            except Exception:                                  # noqa: BLE001
                remove = True
            if remove:
                try:
                    p.unlink()
                    n += 1
                except OSError:
                    pass
        return n

    def clear_project(self, project_id: str) -> int:
        """Alle Einträge entfernen, deren Meta ``project_id`` matcht."""
        n = 0
        if not self.enabled or not project_id:
            return 0
        pid = str(project_id)
        for p in list(self.dir.glob("*.npz")):
            remove = False
            try:
                with np.load(p, allow_pickle=False) as z:
                    if "meta" in z.files:
                        m = json.loads(z["meta"].item().decode("utf-8"))
                        if str(m.get("project_id", "")) == pid:
                            remove = True
            except Exception:                                  # noqa: BLE001
                pass
            if remove:
                try:
                    p.unlink()
                    n += 1
                except OSError:
                    pass
        return n
