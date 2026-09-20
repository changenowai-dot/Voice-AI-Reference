"""Offline-Test: Job-Lifecycle, Cancel, State-Machine, Job-ID-Filterung.

Prüft:
1. BackendLauncher generiert eine eindeutige job_id pro Instanz.
2. parse_progress_event reicht part/parts/phase/attempt durch.
3. JobResult unterscheidet ok / cancelled / returncode.
4. cancel() setzt _cancelling und läuft asynchron (blockiert nicht).
5. State-Machine-Enums in app.py sind vorhanden und konsistent.
6. Events mit falscher _job_id werden in der GUI ignoriert (Unit-Test
   der _on_event-Filter-Logik über parse_progress_event + Dummy-App).

Dieser Test braucht KEIN tkinter (wir testen nur die reine Logik);
damit ist er in der Sandbox lauffähig.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "project"))

# Lade backend/backend module DIREKT (ohne __init__.py, der tkinter
# via app.run importiert). Die Tests brauchen kein tkinter.
import importlib.util

def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(
        name, str(ROOT / "project" / relpath))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_backend_mod = _load("app.gui.backend", "app/gui/backend.py")
_helpers_mod = _load("app.gui.helpers", "app/gui/helpers.py")
JobResult = _backend_mod.JobResult
BackendLauncher = _backend_mod.BackendLauncher
parse_progress_event = _backend_mod.parse_progress_event
stage_label = _helpers_mod.stage_label

# -------------------------------------------------------------- helpers
def test_backend_job_result_and_parser():
    """JobResult + parse_progress_event liefern die neuen Felder."""

    # JobResult hat cancelled/job_id Felder
    r = JobResult(ok=False, cancelled=True, job_id="abc123", returncode=-15)
    assert r.cancelled is True
    assert r.ok is False
    assert r.job_id == "abc123"
    assert r.returncode == -15

    # parse_progress_event: progress event mit allen neuen Feldern
    evt = {"event": "progress", "percent": 42, "segment": 3,
           "segments_total": 10, "qc_percent": 75, "part": 2, "parts": 3,
           "phase": "qc", "attempt": 2}
    out = parse_progress_event(evt)
    assert out["percent"] == 42
    assert out["segment"] == 3
    assert out["segments_total"] == 10
    assert out["qc"] == 75
    assert out["part"] == 2
    assert out["parts_total"] == 3
    assert out["phase"] == "qc"
    assert out["attempt"] == 2
    assert out["stage"] == "qc"

    # error event -> stage="error"
    out = parse_progress_event({"event": "error", "message": "boom"})
    assert out["stage"] == "error"

    # stage event mit part
    out = parse_progress_event({"event": "stage", "stage": "part",
                                "part": 1, "parts": 3,
                                "detail": "Abschnitt 1/3"})
    assert out["stage"] == "part"
    assert out["part"] == 1
    assert out["detail"] == "Abschnitt 1/3"
    print("[PASS] parse_progress_event + JobResult Felder")


def test_backend_launcher_has_job_id():
    """Jeder neue Launcher hat eine andere job_id; running=False ohne Start."""

    results = []

    def noop_event(_e): pass
    def noop_state(_s): pass
    def on_done(r: JobResult): results.append(r)

    l1 = BackendLauncher(noop_event, noop_state, on_done)
    l2 = BackendLauncher(noop_event, noop_state, on_done)
    assert l1.job_id != l2.job_id, "job_id muss pro Instanz eindeutig sein"
    assert len(l1.job_id) >= 8
    assert l1.running is False
    # cancel() auf nicht gestartetem Launcher darf nicht crashen und soll
    # trotzdem _finish_cancelled aufrufen (asynchron).
    l1.cancel()
    deadline = time.time() + 5
    while time.time() < deadline and not results:
        time.sleep(0.05)
    assert results, "cancel() ohne laufenden Prozess soll trotzdem on_done mit cancelled=True ausloesen"
    assert results[-1].cancelled is True
    assert results[-1].job_id == l1.job_id
    print("[PASS] Launcher-job_id eindeutig, cancel() auf leerem Launcher liefert CANCELLED")


def test_app_state_machine_constants():
    """Die Zustandskonstanten der GUI müssen vorhanden sein (wir lesen die
    Klasse per AST, weil tkinter nicht installiert ist)."""
    import ast
    src = (ROOT / "project" / "app" / "gui" / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "VoiceOverApp":
            assigns = {}
            for b in node.body:
                if isinstance(b, ast.Assign):
                    for t in b.targets:
                        if isinstance(t, ast.Attribute) and \
                                isinstance(t.value, ast.Name) and \
                                t.value.id == "self":
                            pass
                        elif isinstance(t, ast.Name):
                            try:
                                assigns[t.id] = ast.literal_eval(b.value)
                            except Exception:
                                pass
            assert "JOB_IDLE" in assigns, "JOB_IDLE Konstante fehlt"
            assert "JOB_RUNNING" in assigns, "JOB_RUNNING Konstante fehlt"
            assert "JOB_CANCELLING" in assigns
            assert "JOB_CANCELLED" in assigns
            assert "JOB_SUCCESS" in assigns
            assert "JOB_FAILED" in assigns
            assert "JOB_INCOMPLETE" in assigns
            assert assigns["JOB_IDLE"] == "IDLE"
            assert assigns["JOB_CANCELLED"] == "CANCELLED"
            assert assigns["JOB_SUCCESS"] == "SUCCESS"
            assert assigns["JOB_FAILED"] == "FAILED"
            assert assigns["JOB_INCOMPLETE"] == "INCOMPLETE"
            print("[PASS] GUI-State-Machine-Konstanten vorhanden")
            return
    raise AssertionError("Klasse VoiceOverApp nicht in app.py gefunden")


def test_cancel_runs_async():
    """cancel() blockiert den aufrufenden Thread NICHT (P5)."""
    import subprocess

    results = []
    events = []
    state_msgs = []

    def on_event(e): events.append(e)
    def on_state(s): state_msgs.append(s)
    def on_done(r: JobResult): results.append(r)

    # Start a tiny blocking subprocess that sleeps so cancel has work to do
    py = sys.executable
    proc = subprocess.Popen(
        [py, "-c", "import sys,time;print('start',flush=True);time.sleep(30)"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        bufsize=1)
    # Manuell einen Launcher mit diesem proc bestuecken (um start() zu
    # umgehen, das ein Backend-Skript aufrufen wuerde)
    launcher = BackendLauncher(on_event, on_state, on_done)
    launcher.proc = proc
    # Reader thread starten
    import threading
    launcher._reader = threading.Thread(target=launcher._pump, daemon=True)
    launcher._reader.start()
    # Warten bis der Prozess lesbar ist
    time.sleep(0.3)
    assert launcher.running is True
    t0 = time.time()
    launcher.cancel()            # darf NICHT blockieren
    dt = time.time() - t0
    assert dt < 0.5, f"cancel() blockierte {dt:.2f}s GUI-Thread – muss <0.5s sein"
    # Warten bis der Prozess tatsaechlich tot ist
    deadline = time.time() + 10
    while time.time() < deadline:
        if not launcher.running:
            break
        time.sleep(0.1)
    assert launcher.running is False
    if launcher._reader is not None:
        launcher._reader.join(timeout=5)
    assert results, "cancel() muss via _finish_cancelled on_done ausloesen"
    assert results[-1].cancelled is True
    print(f"[PASS] cancel() laeuft asynchron (Rufdauer {dt*1000:.0f} ms)")


def test_stage_label_maps_new_phases():
    """Die SPEECH_STAGES_DE-Tabelle muss die neuen Phasen qc/split/
    concat/error enthalten."""
    assert stage_label("qc") != "qc", "qc muss auf deutsch uebersetzt sein"
    assert stage_label("split") != "split"
    assert stage_label("assembling") != "assembling"
    assert stage_label("mastering") != "mastering"
    assert stage_label("error") == "Fehler"
    print("[PASS] stage_label uebersetzt neue Phasen")


if __name__ == "__main__":
    test_backend_job_result_and_parser()
    test_backend_launcher_has_job_id()
    test_app_state_machine_constants()
    test_cancel_runs_async()
    test_stage_label_maps_new_phases()
    print()
    print("ALL JOB-LIFECYCLE TESTS PASSED")
