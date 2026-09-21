"""Tests für den BackendLauncher – insbesondere den PIPE-Deadlock-Fix.

Wir simulieren einen Backend-Prozess, der massiv auf stderr schreibt
(z. B. torch/HF-CUDA-Logs, > 4 KB) und nur wenige JSONL-Events auf
stdout emittet. Vor dem Deadlock-Fix wäre der Kindprozess stecken
geblieben, weil _pump nur stdout las und stderr nicht abfloss.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

# Allow running from project root – wenn tkinter nicht installiert ist
# (CI/Headless), einen Stub einschleusen, damit app.gui.app importiert
# werden kann (wir testen hier nur backend.py, das braucht kein tkinter).
import builtins  # noqa: E402
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

try:  # noqa: E402
    import tkinter as _tk_check  # noqa: F401
except ModuleNotFoundError:
    # Minimaler tkinter-Stub, damit app.py (mit class VoiceOverApp(tk.Tk))
    # auch ohne X11/tkinter installiert importieren kann.
    class _TkStubModule(types.ModuleType):
        TclError = type("TclError", (Exception,), {})
        class Tk: pass
        class Frame: pass
        class StringVar:
            def __init__(self, *a, **kw): pass
            def get(self): return ""
            def set(self, v): pass
        class BooleanVar:
            def __init__(self, *a, **kw): pass
            def get(self): return False
            def set(self, v): pass
        class DoubleVar:
            def __init__(self, *a, **kw): pass
            def get(self): return 1.0
            def set(self, v): pass
        NONE = N = S = E = W = CENTER = LEFT = RIGHT = TOP = BOTTOM = ""
        HORIZONTAL = VERTICAL = BOTH = ALL = END = ""
        X = Y = ""
        DISABLED = NORMAL = ACTIVE = ""
        WORD = ""
        def __getattr__(self, name):
            def _factory(*a, **kw): return None
            return _factory
    import types as _t
    _tk = _TkStubModule("tkinter")
    sys.modules["tkinter"] = _tk
    sys.modules["tkinter.ttk"] = _TkStubModule("tkinter.ttk")
    sys.modules["tkinter.filedialog"] = _TkStubModule("tkinter.filedialog")
    sys.modules["tkinter.messagebox"] = _TkStubModule("tkinter.messagebox")
    # PIL stub
    try:
        from PIL import Image, ImageTk  # noqa: F401
    except Exception:
        _pil = _TkStubModule("PIL")
        _pil.Image = _pil
        _pil.ImageTk = _pil
        sys.modules["PIL"] = _pil
        sys.modules["PIL.Image"] = _pil
        sys.modules["PIL.ImageTk"] = _pil

from app.gui.backend import BackendLauncher, JobResult, backend_args, _child_env  # noqa: E402
from app import paths  # noqa: E402


def _write_noisy_script(path: Path, mode: str = "noise_then_ok") -> None:
    """Schreibt ein Python-Skript, das stderr flutet und dann Events ausgibt.

    Modes:
      - noise_then_ok: viele stderr-Zeilen + startup/text_ready/done → SUCCESS
      - noise_then_error: viele stderr-Zeilen + Exception ohne stdout-error
                         (simuliert Import-/torch-Crash vor erstem Event)
      - quiet_ok: nur Events (Baseline)
    """
    if mode == "noise_then_ok":
        body = """
import sys, time, json
# ~8 KB auf stderr schreiben – mehr als der Standard-Pipe-Buffer (4 KB)
NOISE = "[torch-cuda] cuda runtime initialized cudnn 8.9 " * 30
for i in range(50):
    print(NOISE + f" line {i}", file=sys.stderr, flush=True)
print(json.dumps({"event":"stage","stage":"startup","detail":"Backend gestartet"}), flush=True)
print(json.dumps({"event":"stage","stage":"text_ready","chars":5}), flush=True)
# noch mehr Noise zwischen text_ready und voice_load
for i in range(50):
    print(NOISE + f" mid line {i}", file=sys.stderr, flush=True)
print(json.dumps({"event":"stage","stage":"voice_load","voice":"test"}), flush=True)
print(json.dumps({"event":"stage","stage":"model_ready"}), flush=True)
print(json.dumps({"event":"done","summary":{"ok":True,"wav":"ok.wav"}}), flush=True)
sys.exit(0)
"""
    elif mode == "noise_then_error":
        body = """
import sys, time, json
NOISE = "[hf-import] loading safetensors triton " * 30
for i in range(40):
    print(NOISE + f" line {i}", file=sys.stderr, flush=True)
print(json.dumps({"event":"stage","stage":"startup"}), flush=True)
print(json.dumps({"event":"stage","stage":"text_ready","chars":5}), flush=True)
for i in range(60):
    print(NOISE + f" after-txt line {i}", file=sys.stderr, flush=True)
# Jetzt crashen wir OHNE error-Event auf stdout (simuliert Import-Error
# zwischen text_ready und voice_load, wie der ursprüngliche Bug).
print("RuntimeError: CUDA out of memory", file=sys.stderr, flush=True)
print("Traceback (most recent call last):", file=sys.stderr, flush=True)
print("  File foo.py line 123", file=sys.stderr, flush=True)
sys.exit(7)
"""
    else:  # quiet_ok
        body = """
import sys, json, time
print(json.dumps({"event":"stage","stage":"startup"}), flush=True)
print(json.dumps({"event":"stage","stage":"text_ready","chars":5}), flush=True)
print(json.dumps({"event":"done","summary":{"ok":True}}), flush=True)
sys.exit(0)
"""
    path.write_text(body, encoding="utf-8")


class _Collector:
    def __init__(self):
        self.events = []
        self.states = []
        self.done_result: JobResult | None = None
        self.done_event = threading.Event()
        self.lock = threading.Lock()

    def on_event(self, evt):
        with self.lock:
            self.events.append(evt)

    def on_state(self, msg):
        with self.lock:
            self.states.append(msg)

    def on_done(self, result):
        self.done_result = result
        self.done_event.set()


def _launch_noisy(mode: str, timeout_s: float = 30.0) -> _Collector:
    coll = _Collector()
    with tempfile.TemporaryDirectory() as td:
        script = Path(td) / "fake_backend.py"
        _write_noisy_script(script, mode=mode)
        jobfile = Path(td) / "job.json"
        jobfile.write_text(json.dumps({"text": "hi", "language": "German"}),
                           encoding="utf-8")
        # launcher.start() baut sein cmd via backend_args – das zeigt auf
        # app/main.py. Wir bypassen das nicht; stattdessen rufen wir
        # launchers.proc direkt auf und nutzen einen korrigierten cmd.
        launcher = BackendLauncher(on_event=coll.on_event,
                                   on_state=coll.on_state,
                                   on_done=coll.on_done)
        launcher.job_id = "test" + hex(int(time.time() * 1000))[2:]
        cmd = [sys.executable, "-u", str(script)]
        proc = subprocess.Popen(
            cmd, cwd=str(paths.ROOT),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            bufsize=1, env=_child_env())
        launcher.proc = proc
        launcher._started_at = time.perf_counter()
        launcher._emit_marker_event("WORKER_START", pid=proc.pid)
        launcher._reader = threading.Thread(
            target=launcher._pump, daemon=True, name="test-out")
        launcher._err_reader = threading.Thread(
            target=launcher._pump_stderr, daemon=True, name="test-err")
        launcher._reader.start()
        launcher._err_reader.start()
        finished = coll.done_event.wait(timeout=timeout_s)
        if not finished:
            proc.kill()
            launcher._reader.join(timeout=2)
            launcher._err_reader.join(timeout=2)
            raise AssertionError(
                f"Launcher hängt nach {timeout_s}s (möglicher PIPE-Deadlock) "
                f"bei mode={mode}")
    return coll


def test_noise_then_ok():
    """Massiv stderr-Output darf _pump nicht blockieren."""
    coll = _launch_noisy("noise_then_ok")
    r = coll.done_result
    assert r is not None, "on_done wurde nie aufgerufen"
    assert r.ok, f"Job fehlgeschlagen: error={r.error!r} detail={r.detail[:200]!r}"
    assert r.returncode == 0
    # Events müssen angekommen sein – einschließlich der
    # Marker-Events zur Diagnose.
    kinds = [e.get("event") for e in coll.events]
    assert "done" in kinds, f"done-Event fehlt, events={kinds}"


def test_noise_then_crash_reports_error():
    """Wenn das Kind zwischen text_ready und dem nächsten Event mit
    einem Traceback auf stderr stirbt, MUSS die GUI sofort einen
    sichtbaren Fehler bekommen (kein stiller Hänger auf „Text vorbereitet“)."""
    coll = _launch_noisy("noise_then_error")
    r = coll.done_result
    assert r is not None
    assert not r.ok, "Job hätte fehlschlagen müssen"
    assert not r.cancelled
    assert "Exit-Code 7" in r.error, f"Fehlermeldung sollte Exit-Code nennen: {r.error!r}"
    assert r.detail, "stderr-Tail muss an die GUI gemeldet werden"
    assert "RuntimeError" in r.detail or "Traceback" in r.detail


def test_quiet_ok_baseline():
    coll = _launch_noisy("quiet_ok")
    r = coll.done_result
    assert r is not None
    assert r.ok, f"Baseline fehlgeschlagen: {r.error}"


def test_marker_events_emitted():
    """Für die Diagnostizierbarkeit müssen Marker-Events für die
    wichtigsten Lifecycle-Übergänge ausgesandt werden."""
    coll = _launch_noisy("noise_then_ok")
    markers = [e.get("marker") for e in coll.events
               if e.get("event") == "_marker"]
    # WORKER_START + mindestens einer der Stufen-Marker + JOB_SUCCESS
    assert "WORKER_START" in markers, f"WORKER_START fehlt: {markers}"
    assert "JOB_SUCCESS" in markers, f"JOB_SUCCESS fehlt: {markers}"
    assert any(m in markers for m in ("RUNNER_START", "TEXT_READY",
                                      "TTS_ENGINE_START", "MODEL_READY")), \
        f"kein Stufenmarker: {markers}"


if __name__ == "__main__":
    import traceback
    fails = 0
    for fn in (test_noise_then_ok, test_noise_then_crash_reports_error,
               test_quiet_ok_baseline, test_marker_events_emitted):
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            fails += 1
            print(f"FAIL {fn.__name__}: {e}")
            traceback.print_exc()
    sys.exit(1 if fails else 0)
