"""Projekt-Zustand für Resume (Anforderung 37).

Ein Projekt = eine Eingabedatei. Der Zustand listet alle Segmente mit
Status (pending/done/failed) und Cache-Schlüsseln. Nach Abbruch (z. B.
bei 93 %) werden beim nächsten Start nur fehlende Teile erzeugt.
"""
from __future__ import annotations

import time
from pathlib import Path

from .. import paths
from ..utils import read_json, write_json


def project_id_for(input_path: Path, language: str) -> str:
    from ..utils import sha256_str
    stem = Path(input_path).stem
    digest = sha256_str(f"{Path(input_path).name}:{language}")[:10]
    return f"{stem}__{digest}"


class ProjectState:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.path = paths.CACHE_PROJECT_DIR / f"{project_id}.json"
        self.data: dict = read_json(self.path, {}) or {}

    # -- Lebenszyklus ---------------------------------------------------------
    def init_segments(self, segment_metas: list[dict], config_snapshot: dict,
                      input_file: str) -> None:
        """Initialisiert (oder setzt fort) den Projektzustand.

        Bereits 'done' Segmente bleiben erhalten, solange Text-Hash und
        Cache-Schlüssel übereinstimmen (Resume)."""
        old = {s.get("index"): s for s in self.data.get("segments", [])}
        segments = []
        for meta in segment_metas:
            idx = meta["index"]
            prev = old.get(idx)
            if (prev and prev.get("status") == "done"
                    and prev.get("text_hash") == meta.get("text_hash")
                    and prev.get("cache_key") == meta.get("cache_key")):
                segments.append(prev)             # wiederverwenden
            else:
                segments.append({
                    "index": idx,
                    "status": "pending",
                    "text_hash": meta.get("text_hash"),
                    "cache_key": meta.get("cache_key"),
                    "preview": meta.get("preview", "")[:80],
                    "pause_after_s": meta.get("pause_after_s", 0.5),
                    "score": None,
                    "attempts": 0,
                })
        self.data = {
            "project_id": self.project_id,
            "input_file": input_file,
            "config": config_snapshot,
            "segments": segments,
            "created_at": self.data.get("created_at") or time.strftime(
                "%Y-%m-%d %H:%M:%S"),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "phase": "segments_ready",
        }
        self.save()

    def set_segment(self, index: int, status: str, score: float | None = None,
                    attempts: int = 0, error: str = "") -> None:
        for seg in self.data.get("segments", []):
            if seg["index"] == index:
                seg["status"] = status
                seg["score"] = score
                seg["attempts"] = attempts
                if error:
                    seg["error"] = error[:500]
                break
        self.data["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.save()

    def done_indices(self) -> set[int]:
        return {s["index"] for s in self.data.get("segments", [])
                if s.get("status") == "done"}

    def summary(self) -> dict:
        segs = self.data.get("segments", [])
        done = [s for s in segs if s.get("status") == "done"]
        failed = [s for s in segs if s.get("status") == "failed"]
        scores = [s["score"] for s in done if s.get("score") is not None]
        return {
            "project_id": self.project_id,
            "input_file": self.data.get("input_file"),
            "total": len(segs),
            "done": len(done),
            "failed": len(failed),
            "pending": len(segs) - len(done) - len(failed),
            "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
            "phase": self.data.get("phase"),
            "updated_at": self.data.get("updated_at"),
        }

    # -- Persistenz ------------------------------------------------------------
    def save(self) -> None:
        write_json(self.path, self.data)

    def set_phase(self, phase: str, **extra) -> None:
        self.data["phase"] = phase
        self.data.update(extra)
        self.save()
