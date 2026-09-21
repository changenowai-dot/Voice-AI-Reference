"""Backend-Launcher der GUI (§16): genau EIN Backend-Prozess.

Startet ``<python> app/main.py --job <jobfile>`` als Subprocess, liest
stdout (JSONL-Ereignisse) UND stderr (Diagnose) in getrennten
Threads threadsicher und meldet Ereignisse an die GUI zurück. Dies
behebt den klassischen PIPE-Deadlock, bei dem der Kindprozess stecken
blieb, sobald stderr voll war (insbesondere beim ersten
torch/HF-Import mit vielen CUDA/Modell-Meldungen) und _pump() nur
stdout las.

Jeder Start erzeugt eine neue BackendLauncher-Instanz mit eigener
Job-ID; Events werden an den Callback weitergereicht – die GUI ist
dafür verantwortlich, Events mit veralteter job_id zu ignorieren.
Cancel läuft auf einem eigenen Thread, damit der GUI-Thread nie
blockiert.

Diagnose-Marker für den Lifecycle (gefordert, keine still
verschluckten Exceptions):
  GUI_SUBMIT → JOB_CREATED → WORKER_START → RUNNER_START →
  PIPELINE_START → TTS_ENGINE_START → MODEL_READY → REFERENCE_READY →
  QWEN_GENERATE_START → QWEN_GENERATE_END → WAV_WRITE → JOB_SUCCESS
  sowie JOB_FAIL / WORKER_EXCEPTION / RUNNER_EXCEPTION mit Traceback.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .. import paths

EventCb = Callable[[dict], None]
StateCb = Callable[[str], None]

log = logging.getLogger("voiceover.gui.backend")

# Marker, die wir explizit an die GUI weiterreichen bzw. im Verlauf
# tracken. Jede Phase bekommt einen eigenen Log-Eintrag, damit ein
# Hänger exakt lokalisiert werden kann.
_TRANSITION_MARKERS = {
    "startup":       "RUNNER_START",
    "text_ready":    "TEXT_READY",
    "voice_load":    "TTS_ENGINE_START",
    "model_load":    "MODEL_LOAD",
    "model_ready":   "MODEL_READY",
    "split":         "SPLIT",
    "part":          "PART",
    "tts":           "QWEN_GENERATE_START",
    "qc":            "QC",
    "assembling":    "ASSEMBLING",
    "mastering":     "MASTERING",
    "speed":         "SPEED",
    "concat":        "CONCAT",
    "concat_done":   "CONCAT_DONE",
    "done":          "JOB_SUCCESS",
    "error":         "JOB_FAIL",
}


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
    # -u = unbuffered stdout/stderr, damit JSONL-Events sofort bei der
    # GUI ankommen (sonst kann Python bei PIPE block-puffern und wir
    # warten ewig auf das erste Event).
    return [py, "-u", str(paths.APP_DIR / "main.py"), "--job", str(job_file)]


def _child_env() -> dict:
    """Umgebung für den Kindprozess – PYTHONUNBUFFERED setzen,
    damit selbst bei vergessenem flush=… Events sofort ankommen."""
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    return env


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

    # Maximal zu behaltende stderr-Zeichen für Diagnose (wird im Fehlerfall
    # an die GUI gemeldet, damit ein stiller Absturz einen sichtbaren
    # Grund hat).
    STDERR_TAIL = 8000

    def __init__(self, on_event: EventCb, on_state: StateCb,
                 on_done: Callable[[JobResult], None]):
        self.job_id = uuid.uuid4().hex[:10]
        self.proc: subprocess.Popen | None = None
        self._on_event = on_event
        self._on_state = on_state
        self._on_done = on_done
        self._reader: threading.Thread | None = None
        self._err_reader: threading.Thread | None = None
        self._cancelling = threading.Event()
        self._done_called = False
        self._lock = threading.Lock()
        # stderr wird asynchron gesammelt (paralleler Thread → kein
        # PIPE-Deadlock mehr).
        self._stderr_buf: deque[str] = deque(maxlen=2000)
        self._stderr_lock = threading.Lock()
        self._last_marker: str = ""
        self._started_at: float = 0.0
        # Für Fehlerfälle: erste Exception (inkl. Traceback) aus stderr.
        self._first_traceback: str = ""

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
        log.info("GUI_SUBMIT job_id=%s cmd=%r voice=%s lang=%s chars=%d",
                 self.job_id, cmd, spec.get("voice_id"),
                 spec.get("language"), len(spec.get("text", "")))
        self._on_state(f"Backend wird gestartet …")
        self._started_at = time.perf_counter()
        self._emit_marker_event("JOB_CREATED", job_id=self.job_id,
                                voice_id=spec.get("voice_id"))
        # CREATE_NO_WINDOW on Windows to avoid popping up a console
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.proc = subprocess.Popen(
            cmd, cwd=str(paths.ROOT),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            bufsize=1, creationflags=creationflags,
            env=_child_env())
        # PIPE-Deadlock-Fix: stdout UND stderr in je einem Thread lesen.
        # Vorher las _pump nur stdout; stderr.read() wurde erst nach
        # proc.wait() aufgerufen. Sobald torch/HF beim ersten Import
        # mehr als den OS-Pipe-Puffer (Windows ~4 KB) an Logs schrieb
        # (CUDA, cuDNN, SafeTensors, Modell-Load), blockierte der
        # Kindprozess beim write() auf stderr – der GUI-Status blieb
        # für immer auf „Text vorbereitet“ stehen, weil _pump auf die
        # nächste stdout-Zeile wartete und proc.wait() nie zurückkam.
        self._reader = threading.Thread(target=self._pump, daemon=True,
                                        name=f"backend-out-{self.job_id}")
        self._err_reader = threading.Thread(target=self._pump_stderr, daemon=True,
                                            name=f"backend-err-{self.job_id}")
        self._emit_marker_event("WORKER_START", pid=self.proc.pid)
        self._reader.start()
        self._err_reader.start()

    # ------------------------------------------------------------------
    def _emit_marker_event(self, marker: str, **extra) -> None:
        """Internen Diagnose-Marker als GUI-Event weiterreichen."""
        self._last_marker = marker
        try:
            self._on_event({
                "event": "_marker",
                "marker": marker,
                "ts": time.time(),
                "elapsed_s": round(time.perf_counter() - self._started_at, 3)
                               if self._started_at else 0.0,
                "job_id": self.job_id,
                **extra,
            })
        except Exception:                              # noqa: BLE001
            pass

    def _pump_stderr(self) -> None:
        """Liest stderr parallel – verhindert PIPE-Deadlock.

        Geschriebene Zeilen werden an den Logger geschickt und in
        einem Ringpuffer gehalten, damit im Fehlerfall ein brauchbarer
        Traceback an die GUI gemeldet werden kann.
        """
        assert self.proc and self.proc.stderr
        try:
            for line in self.proc.stderr:
                if not line:
                    continue
                line = line.rstrip("\n")
                with self._stderr_lock:
                    self._stderr_buf.append(line)
                # Traceback-Zeilen als Fehlerquelle merken (für die
                # Abschluss-Meldung an die GUI).
                if ("Traceback" in line or "Error:" in line
                        or "RuntimeError:" in line):
                    if not self._first_traceback:
                        self._first_traceback = line
                # An den internen Logger weitergeben – nicht ins GUI
                # (sonst würde jedes INFO-Log den Fortschrittsbalken
                # überfluten).
                try:
                    log.debug("[backend:%s] %s", self.job_id[:6], line)
                except Exception:                          # noqa: BLE001
                    pass
        except Exception as e:                            # noqa: BLE001
            log.warning("_pump_stderr exception: %s", e)

    def _stderr_tail(self, max_chars: int | None = None) -> str:
        n = max_chars if max_chars is not None else self.STDERR_TAIL
        with self._stderr_lock:
            text = "\n".join(self._stderr_buf)
        if len(text) > n:
            text = "…" + text[-n:]
        return text

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
        self._emit_marker_event("CANCEL")
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
        # beide reader durch EOF aufwachen lassen
        for t in (self._reader, self._err_reader):
            if t is not None:
                t.join(timeout=3)
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
        pump_exc: str = ""
        last_stage: str = ""
        try:
            for line in self.proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    # Nicht-JSON-Zeilen auf stdout gehören nicht ins
                    # Event-Protokoll (z. B. verirrte print-Ausgaben).
                    with self._stderr_lock:
                        self._stderr_buf.append("[stdout] " + line)
                    continue
                # Tag event with our job_id
                evt["_job_id"] = self.job_id
                kind = evt.get("event")
                stage = evt.get("stage") if kind == "stage" else None
                if stage and stage != last_stage:
                    last_stage = stage
                    marker = _TRANSITION_MARKERS.get(stage)
                    if marker:
                        self._emit_marker_event(marker, stage=stage,
                                                detail=evt.get("detail", ""))
                if kind == "error":
                    self._emit_marker_event("RUNNER_EXCEPTION",
                                            message=evt.get("message", "")[:300])
                    if not self._cancelling.is_set():
                        result.error = str(evt.get("message", ""))
                        result.detail = str(evt.get("detail", ""))
                    try:
                        self._on_event(evt)
                    except Exception:                      # noqa: BLE001
                        pass
                elif kind == "done":
                    summ = evt.get("summary", {}) or {}
                    result.ok = bool(summ.get("ok", True))
                    if not result.ok:
                        result.error = (summ.get("status") or "INCOMPLETE")
                        result.detail = json.dumps(summ, ensure_ascii=False)[:2000]
                        self._emit_marker_event("JOB_FAIL",
                                                status=result.error)
                    else:
                        self._emit_marker_event("JOB_SUCCESS",
                                                wav=bool(summ.get("wav")))
                    result.summary = summ
                    try:
                        self._on_event(evt)
                    except Exception:                      # noqa: BLE001
                        pass
                else:
                    try:
                        self._on_event(evt)
                    except Exception as e:                  # noqa: BLE001
                        # Callback-Fehler NIE verschlucken – sonst hängt
                        # die GUI ewig im LÄUFT…-Zustand.
                        pump_exc = f"on_event exception: {e!r}"
                        log.exception("on_event raised for %s", kind)
                if self._cancelling.is_set() and not cancelled_by_user:
                    cancelled_by_user = True
        except Exception as e:                            # noqa: BLE001
            pump_exc = f"_pump exception: {e!r}"
            log.exception("_pump raised")
            self._emit_marker_event("WORKER_EXCEPTION", detail=pump_exc)

        # Prozess-Ende abwarten. stderr wird bereits parallel gelesen,
        # also ist wait() jetzt DEADLOCK-FREI.
        rc = -1
        try:
            rc = self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            try:
                self.proc.kill()
                rc = self.proc.wait(timeout=5)
            except Exception:
                rc = -1

        # Sicherstellen, dass der stderr-Reader fertig ist (EOF).
        if self._err_reader is not None:
            self._err_reader.join(timeout=5)

        err_out = self._stderr_tail()
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
        elif pump_exc and not result.error:
            result.ok = False
            result.error = pump_exc
            result.detail = err_out
        elif rc != 0 and not result.error:
            # Kind ist mit Fehlercode abgestürzt (z. B. Import-Error
            # oder nicht abgefangene Exception). Statt still auf
            # „Text vorbereitet“ stehen zu bleiben, einen klaren
            # Fehler mit stderr-Traceback an die GUI melden.
            result.ok = False
            tb_hint = self._first_traceback or err_out.strip().split("\n")[-1] if err_out else ""
            result.error = (f"Backend-Prozess unerwartet beendet "
                            f"(Exit-Code {rc}).")
            if tb_hint:
                result.error += f"  Letzte Fehlermeldung: {tb_hint[:300]}"
            result.detail = err_out
            self._emit_marker_event("JOB_FAIL", returncode=rc,
                                    last_marker=self._last_marker,
                                    traceback=tb_hint[:500])

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
