"""Backend-Launcher der GUI (§16): genau EIN Backend-Prozess.

Startet ``<python> app/main.py --job <jobfile>`` als Subprocess, liest
stdout (JSONL-Ereignisse) und stderr (Diagnose) threadsicher und
meldet Ereignisse an die GUI zurück. Kein zweiter Prozess, solange
einer läuft (GUI-seitig erzwungen + backendseitige Sperrdatei).

Jeder Start erzeugt eine neue BackendLauncher-Instanz mit eigener
Job-ID; Events werden an den Callback weitergereicht – die GUI ist
dafür verantwortlich, Events mit veralteter job_id zu ignorieren.
Cancel läuft auf einem eigenen Thread, damit der GUI-Thread nie
blockiert.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .. import paths

EventCb = Callable[[dict], None]
StateCb = Callable[[str], None]


BACKEND_EXE_NAME = "VoiceOverAppBackend.exe"


def backend_python() -> str:
    """Backend-Programm für Jobs (JSONL auf stdout!).

    Eingefrorene App (§7/§8 Packaging): die GUI-EXE ist windowed
    (ohne Konsolen-stdout). Damit das Backend zuverlässig JSONL auf
    stdout schreiben kann, wird die im selben Ordner mitgebaute
    KONSolen-EXE VoiceOverAppBackend.exe verwendet; nur als Fallback
    die eigene EXE. Quellmodus: .venv-Python.
    """
    if getattr(sys, "frozen", False):
        backend_exe = Path(sys.executable).parent / BACKEND_EXE_NAME
        if backend_exe.exists():
            return str(backend_exe)
        return sys.executable
    venv = paths.ROOT / ".venv" / "Scripts" / "python.exe"
    if venv.exists():
        return str(venv)
    return sys.executable


def backend_args(job_file: Path) -> list[str]:
    py = backend_python()
    if getattr(sys, "frozen", False):
        return [py, "--job", str(job_file)]
    return [py, str(paths.APP_DIR / "main.py"), "--job", str(job_file)]


@dataclass
class JobResult:
    ok: bool = False
    cancelled: bool = False           # P5/P12: expliziter Abbruch-State
    summary: dict = field(default_factory=dict)
    error: str = ""
    detail: str = ""
    returncode: int = -1
    job_id: str = ""


class BackendLauncher:
    """Genau eine Job-Instanz. Pro Job neu erstellen."""

    def __init__(self, on_event: EventCb, on_state: StateCb,
                 on_done: Callable[[JobResult], None]):
        self.job_id = uuid.uuid4().hex[:10]
        self.proc: subprocess.Popen | None = None
        self._on_event = on_event
        self._on_state = on_state
        self._on_done = on_done
        self._reader: threading.Thread | None = None
        self._cancelling = threading.Event()
        self._done_called = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return bool(self.proc and self.proc.poll() is None
                    and not self._done_called)

    def start(self, spec: dict) -> None:
        if self.running:
            raise RuntimeError("Es läuft bereits ein Backend-Prozess (§16).")
        paths.STATE_DIR.mkdir(parents=True, exist_ok=True)
        # Mark every event in this job
        spec = dict(spec)
        spec["_job_id"] = self.job_id
        job_file = paths.STATE_DIR / f"job_{self.job_id}_{int(time.time()*1000)}.json"
        job_file.write_text(json.dumps(spec, ensure_ascii=False),
                            encoding="utf-8")
        cmd = backend_args(job_file)
        self._on_state(f"Backend wird gestartet …")
        # CREATE_NO_WINDOW on Windows to avoid popping up a console
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.proc = subprocess.Popen(
            cmd, cwd=str(paths.ROOT),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            bufsize=1, creationflags=creationflags)
        self._reader = threading.Thread(target=self._pump, daemon=True,
                                        name=f"backend-reader-{self.job_id}")
        self._reader.start()

    def cancel(self) -> None:
        """Cancel asynchron – blockiert GUI-Thread NICHT (P5)."""
        if self._cancelling.is_set():
            return
        self._cancelling.set()
        self._on_state("Abgebrochen – Prozess wird beendet …")
        threading.Thread(target=self._cancel_worker, daemon=True,
                         name=f"backend-cancel-{self.job_id}").start()

    def _cancel_worker(self) -> None:
        """Führe terminate/wait/kill in einem Hintergrundthread aus."""
        if not self.proc:
            self._finish_cancelled()
            return
        if self.proc.poll() is None:
            try:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        self.proc.kill()
                        self.proc.wait(timeout=3)
                    except Exception:
                        pass
            except OSError:
                pass
        # reader thread wird durch stdout-EOF aufwachen und _finish_cancelled
        # via _pump aufrufen; falls er schon tot ist, hier selbst aufrufen
        if self._reader is not None:
            self._reader.join(timeout=3)
        if not self._done_called:
            self._finish_cancelled()

    def _finish_cancelled(self) -> None:
        with self._lock:
            if self._done_called:
                return
            self._done_called = True
        result = JobResult(ok=False, cancelled=True,
                           error="CANCELLED",
                           returncode=getattr(self.proc, "returncode", -15)
                                     if self.proc else -15,
                           job_id=self.job_id,
                           summary={"status": "CANCELLED", "ok": False,
                                    "cancelled": True})
        try:
            self._on_done(result)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _pump(self) -> None:
        assert self.proc and self.proc.stdout
        result = JobResult(job_id=self.job_id)
        cancelled_by_user = False
        try:
            for line in self.proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Tag event with our job_id
                evt["_job_id"] = self.job_id
                kind = evt.get("event")
                if kind == "error":
                    if not self._cancelling.is_set():
                        result.error = str(evt.get("message", ""))
                        result.detail = str(evt.get("detail", ""))
                    self._on_event(evt)
                elif kind == "done":
                    summ = evt.get("summary", {}) or {}
                    result.ok = bool(summ.get("ok", True))
                    if not result.ok:
                        result.error = (summ.get("status") or "INCOMPLETE")
                        result.detail = json.dumps(summ, ensure_ascii=False)[:2000]
                    result.summary = summ
                    self._on_event(evt)
                else:
                    self._on_event(evt)
                if self._cancelling.is_set() and not cancelled_by_user:
                    cancelled_by_user = True
        except Exception:
            pass
        rc = -1
        try:
            rc = self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            try:
                self.proc.kill()
                rc = self.proc.wait(timeout=5)
            except Exception:
                rc = -1
        err_out = ""
        if self.proc.stderr:
            try:
                err_out = self.proc.stderr.read()[-4000:]
            except Exception:
                pass
        result.returncode = rc
        # Wenn explizit gecancelt wurde, immer cancelled=True
        if self._cancelling.is_set():
            result.cancelled = True
            result.ok = False
            if not result.error or result.error == self.proc.__class__.__name__:
                result.error = "CANCELLED"
            result.summary = dict(result.summary or {})
            result.summary["status"] = "CANCELLED"
            result.summary["ok"] = False
            result.summary["cancelled"] = True
        elif not result.ok and not result.error:
            result.error = f"Backend unerwartet beendet (Code {rc})."
            result.detail = err_out
        try:
            self._on_done(result)
        except Exception:
            pass


def parse_progress_event(evt: dict) -> dict:
    """Extrahiert GUI-relevante Fortschrittsfelder (testbar, §17)."""
    out = {}
    if evt.get("event") == "progress":
        out = {"stage": evt.get("stage") or evt.get("phase"),
               "percent": evt.get("percent") or evt.get("tts_percent"),
               "segment": evt.get("segment"),
               "segments_total": evt.get("segments_total"),
               "qc": evt.get("qc_percent"),
               "part": evt.get("part"),
               "parts_total": evt.get("parts"),
               "phase": evt.get("phase"),
               "attempt": evt.get("attempt")}
    elif evt.get("event") == "stage":
        out = {"stage": evt.get("stage"),
               "detail": evt.get("detail", ""),
               "part": evt.get("part"),
               "parts_total": evt.get("parts")}
    elif evt.get("event") == "error":
        out = {"stage": "error",
               "detail": evt.get("message", "")}
    return out
