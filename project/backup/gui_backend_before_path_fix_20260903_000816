"""Backend-Launcher der GUI (§16): genau EIN Backend-Prozess.

Startet ``<python> app/main.py --job <jobfile>`` als Subprocess, liest
stdout (JSONL-Ereignisse) und stderr (Diagnose) threadsicher und
meldet Ereignisse an die GUI zurück. Kein zweiter Prozess, solange
einer läuft (GUI-seitig erzwungen + backendseitige Sperrdatei).
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
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
        # beide EXEs routen CLI-Argumente über desktop.py -> app.main
        return [py, "--job", str(job_file)]
    return [py, str(paths.APP_DIR / "main.py"), "--job", str(job_file)]


@dataclass
class JobResult:
    ok: bool = False
    summary: dict = field(default_factory=dict)
    error: str = ""
    detail: str = ""
    returncode: int = -1


class BackendLauncher:
    def __init__(self, on_event: EventCb, on_state: StateCb,
                 on_done: Callable[[JobResult], None]):
        self.proc: subprocess.Popen | None = None
        self._on_event = on_event
        self._on_state = on_state
        self._on_done = on_done
        self._reader: threading.Thread | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return bool(self.proc and self.proc.poll() is None)

    def start(self, spec: dict) -> None:
        if self.running:
            raise RuntimeError("Es läuft bereits ein Backend-Prozess (§16).")
        paths.STATE_DIR.mkdir(parents=True, exist_ok=True)
        job_file = paths.STATE_DIR / f"job_{int(time.time() * 1000)}.json"
        job_file.write_text(json.dumps(spec, ensure_ascii=False),
                            encoding="utf-8")
        cmd = backend_args(job_file)
        self._on_state(f"Backend gestartet: …main.py --job")
        self.proc = subprocess.Popen(
            cmd, cwd=str(paths.ROOT),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            bufsize=1)
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()

    def cancel(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
            except OSError:
                pass
        self._on_state("Backend beendet (abgebrochen) – Resume möglich")

    # ------------------------------------------------------------------
    def _pump(self) -> None:
        assert self.proc and self.proc.stdout
        result = JobResult()
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue                      # Diagnosezeile ignorieren
            kind = evt.get("event")
            if kind == "error":
                result.error = str(evt.get("message", ""))
                result.detail = str(evt.get("detail", ""))
                self._on_event(evt)
            elif kind == "done":
                result.ok = True
                result.summary = evt.get("summary", {}) or {}
                result.returncode = 0
                self._on_event(evt)
            else:
                self._on_event(evt)
        rc = self.proc.wait()
        err_out = ""
        if self.proc.stderr:
            try:
                err_out = self.proc.stderr.read()[-4000:]
            except Exception:                           # noqa: BLE001
                pass
        if not result.ok and not result.error:
            result.error = (f"Backend unerwartet beendet (Code {rc}).")
            result.detail = err_out
        result.returncode = rc
        try:
            self._on_done(result)
        except Exception:                               # noqa: BLE001
            pass


def parse_progress_event(evt: dict) -> dict:
    """Extrahiert GUI-relevante Fortschrittsfelder (testbar, §17)."""
    out = {}
    if evt.get("event") == "progress":
        out = {"stage": evt.get("stage"),
               "percent": evt.get("percent") or evt.get("tts_percent"),
               "segment": evt.get("segment"),
               "segments_total": evt.get("segments_total"),
               "qc": evt.get("qc_percent")}
    elif evt.get("event") == "stage":
        out = {"stage": evt.get("stage"),
               "detail": evt.get("detail", "")}
    return out
