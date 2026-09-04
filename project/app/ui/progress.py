"""Thread-sicherer Fortschritts-Reporter (Anforderung 31).

Zentraler Zustand für UI-Polling: Datei- und Segment-Fortschritt,
TTS-/QC-Prozent, Gesamtfortschritt, Ereignis-Ringpuffer, Abbruchflag.
"""
from __future__ import annotations

import threading
import time
from collections import deque


class ProgressReporter:
    def __init__(self):
        self._lock = threading.RLock()
        self._data: dict = {
            "running": False,
            "phase": "idle",
            "files_total": 0,
            "files_done": 0,
            "file_index": 0,
            "current_file": None,
            "current_segment": 0,
            "total_segments": 0,
            "tts_percent": 0,
            "qc_percent": 0,
            "overall_percent": 0,
            "started_at": None,
            "finished_at": None,
            "last_error": None,
            "last_summary": None,
        }
        self._events: deque = deque(maxlen=200)
        self._cancel = threading.Event()

    def update(self, **kw) -> None:
        with self._lock:
            if kw.get("running") and not self._data.get("running"):
                self._data["started_at"] = time.strftime("%H:%M:%S")
                self._cancel.clear()
            self._data.update(kw)
            interesting = {k: kw[k] for k in
                           ("phase", "current_file", "file_done", "last_error")
                           if k in kw}
            if interesting:
                self._events.append({
                    "t": time.strftime("%H:%M:%S"), **interesting})

    def event(self, msg: str) -> None:
        with self._lock:
            self._events.append({"t": time.strftime("%H:%M:%S"),
                                 "phase": msg})

    def snapshot(self) -> dict:
        with self._lock:
            out = dict(self._data)
            out["events"] = list(self._events)[-30:]
            out["cancelled"] = self._cancel.is_set()
            return out

    # -- Abbruch (kooperativ) -------------------------------------------------
    def request_cancel(self) -> None:
        self._cancel.set()

    def should_cancel(self) -> bool:
        return self._cancel.is_set()

    def reset(self) -> None:
        with self._lock:
            for k in ("files_total", "files_done", "file_index",
                      "current_segment", "total_segments", "tts_percent",
                      "qc_percent", "overall_percent"):
                self._data[k] = 0
            self._data["current_file"] = None
            self._data["last_error"] = None
