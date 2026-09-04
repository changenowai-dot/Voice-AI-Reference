"""Tests: Konfiguration, Hardware, Cache-Verwaltung, Benchmarks, UI-API."""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from app import paths


def test_config_defaults_and_merge():
    from app import config as cfgmod
    cfgmod.write_default_config_if_missing()
    cfg = cfgmod.load_config()
    assert cfg["language"] in ("German", "English")
    assert cfg["preset"] == "deep_documentary"
    assert cfg["voice_profile"] == "default_best_narrator"
    assert 0.8 <= cfg["speed"] <= 1.2
    assert cfg["emotion"] == "AUTO" and cfg["intensity"] == "AUTO"
    assert cfg["advanced"]["target_lufs"] == -14.0
    updated = cfgmod.update_config({"speed": 1.1,
                                    "advanced": {"segment_target_chars": 500}})
    assert updated["speed"] == 1.1
    assert updated["advanced"]["segment_target_chars"] == 500
    assert updated["advanced"]["segment_max_chars"] == 700   # unverändert
    cfgmod.reset_config()
    assert cfgmod.load_config()["speed"] == 1.0


def test_hardware_detection():
    from app.hardware.detector import (detect_hardware, recommend_model_size,
                                       vram_snapshot)
    hw = detect_hardware()
    assert hw.mode in ("gpu", "gpu_conservative", "cpu")
    assert hw.cpu_threads >= 1
    assert hw.ram_total_gb > 0
    # CPU-Sandbox: keine GPU annehmen!
    free, total = vram_snapshot()
    assert total == 0.0            # ohne CUDA
    if hw.mode == "cpu":
        assert recommend_model_size(hw, "auto") == "0.6B"
    assert recommend_model_size(hw, "1.7B") == "1.7B"   # manuell bleibt


def test_vram_guard_noop_cpu():
    from app.hardware.monitor import ResourcePolicy, VRAMGuard
    g = VRAMGuard(ResourcePolicy())
    g.start()
    rec = g.before_call()          # CPU: darf nicht crashen
    assert rec["batch_size"] == 1
    g.emergency_cleanup()          # ohne CUDA: stiller No-Op
    g.stop()


def test_cache_manager_operations():
    import numpy as np
    from app.cache.manager import CacheManager, segment_cache_key
    cm = CacheManager(enabled=True)
    key = segment_cache_key(engine="e", engine_version="v", model_size="1.7B",
                            speaker="Ryan", instruct="i", language="German",
                            text="Beispieltext", sampling={"t": 1},
                            param_version="v1")
    wav = np.linspace(-0.5, 0.5, 2400, dtype=np.float32)
    cm.put(key, wav, 24000, {"ok": True, "score": 90.0})
    got = cm.get(key)
    assert got is not None
    w2, sr2, meta = got
    assert sr2 == 24000 and meta["score"] == 90.0
    assert cm.has(key)
    assert cm.clear_segment(key)
    assert not cm.has(key)
    stats = cm.stats()
    assert "segments" in stats
    # failed-Clear: Eintrag ohne ok
    cm.put(key, wav, 24000, {"ok": False})
    assert cm.clear_failed() >= 1
    assert not cm.has(key)


def test_cache_clear_all_with_stats():
    import numpy as np
    from app.cache.manager import CacheManager
    cm = CacheManager(enabled=True)
    wav = np.zeros(2400, dtype=np.float32)
    cm.put("testkey1", wav, 24000, {"ok": True})
    cm.put("testkey2", wav, 24000, {"ok": True})
    n = cm.clear_all()               # CLEAR ALL: entfernt alles, auch Fremdes
    assert n >= 2
    assert cm.stats()["segments"] == 0


def test_system_benchmark_quick():
    from app.benchmark.system import run_system_benchmark
    from app.hardware.detector import detect_hardware
    from app.tts.test_double import TestDoubleEngine
    hw = detect_hardware()
    rep = run_system_benchmark(lambda size: TestDoubleEngine(), quick=True, hw=hw)
    assert rep["steps"]["model_load"]["ok"]
    assert rep["steps"]["german_test"]["ok"]
    assert rep["steps"]["english_test"]["ok"]
    assert rep["steps"]["wav_mp3"]["ok"]
    assert (paths.BENCHMARK_DIR / "report_SYSTEM.md").exists()
    assert (paths.BENCHMARK_DIR / "system_benchmark.json").exists()
    assert paths.ENVIRONMENT_FILE.exists()


def test_voice_benchmark_quick():
    from app.tts.test_double import TestDoubleEngine
    from app.voices.benchmark import run_voice_benchmark
    rep = run_voice_benchmark(TestDoubleEngine(),
                              speakers=["Ryan", "Serena"], quick=True)
    assert "Ryan" in rep["speakers"] and "Serena" in rep["speakers"]
    assert rep["recommendation"]["best_male"]
    assert (paths.BENCHMARK_DIR / "voice_benchmark.md").exists()
    # hörbare Proben erzeugt
    files = list((paths.BENCHMARK_DIR / "voices").glob("Ryan_de_*.wav"))
    assert files


def test_project_state_resume_logic():
    from app.project.state import ProjectState
    st = ProjectState("testproj")
    st.init_segments([
        {"index": 0, "text_hash": "a", "cache_key": "k0", "preview": "p0",
         "pause_after_s": 0.4},
        {"index": 1, "text_hash": "b", "cache_key": "k1", "preview": "p1",
         "pause_after_s": 0.4},
    ], {"language": "German"}, "x.txt")
    st.set_segment(0, "done", score=88.0)
    assert st.done_indices() == {0}
    # Neu-Initialisierung mit identischen Hashes behält 'done'
    st2 = ProjectState("testproj")
    st2.init_segments([
        {"index": 0, "text_hash": "a", "cache_key": "k0", "preview": "p0",
         "pause_after_s": 0.4},
        {"index": 1, "text_hash": "b", "cache_key": "k1", "preview": "p1",
         "pause_after_s": 0.4},
    ], {"language": "German"}, "x.txt")
    assert st2.done_indices() == {0}
    st2.set_segment(1, "done", score=91.0)
    # Geänderte Texte -> nur betroffene Segmente werden pending
    st3 = ProjectState("testproj")
    st3.init_segments([
        {"index": 0, "text_hash": "ANDERS", "cache_key": "k0", "preview": "",
         "pause_after_s": 0.4},
        {"index": 1, "text_hash": "b", "cache_key": "k1", "preview": "",
         "pause_after_s": 0.4},
    ], {}, "x.txt")
    assert st3.done_indices() == {1}
    assert st3.summary()["total"] == 2


def test_ui_server_end2end():
    """Vollständiger UI-/API-Test mit TestDouble-Engine (echter HTTP)."""
    port = 8797
    env = dict(__import__("os").environ)
    proc = subprocess.Popen(
        [sys.executable, str(APP_ROOT() / "app" / "main.py"),
         "--webserver", "--engine", "test_double", "--no-browser",
         "--port", str(port)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        base = f"http://127.0.0.1:{port}"
        # auf Server warten
        for _ in range(60):
            try:
                urllib.request.urlopen(base + "/api/status", timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise AssertionError("Server startete nicht")

        def post(path, payload):
            req = urllib.request.Request(
                base + path, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=30).read())

        def get(path):
            return json.loads(urllib.request.urlopen(base + path, timeout=30).read())

        # Konfiguration
        cfgd = get("/api/config")
        assert cfgd["default_profile"] == "male_1"
        assert len(cfgd["profiles"]) == 6

        # Upload (Drag&Drop-Pfad)
        r = post("/api/upload", {"name": "ui_test.txt",
                                 "content": "Dies ist ein UI-Testtext mit "
                                            "genug Inhalt. " * 12})
        assert r["ok"]

        # Aussprache-API
        r = post("/api/pronunciation", {"action": "add", "term": "UITestname",
                                        "value": "ui-test-na-me"})
        assert r["ok"] and "UITestname" in r["user"]
        r = post("/api/pronunciation", {"action": "delete", "term": "UITestname"})
        assert r["ok"]

        # Sicherheit: Cache-Clear ohne confirm wird abgelehnt
        try:
            post("/api/cache/clear", {"scope": "all"})
            raised = False
        except urllib.error.HTTPError:
            raised = True
        assert raised

        # Start + Fortschritt abwarten
        r = post("/api/start", {"language": "German",
                                "preset": "deep_documentary"})
        assert r["ok"]
        deadline = time.time() + 300
        while time.time() < deadline:
            s = get("/api/status")
            if not s["running"] and s.get("files_total", 0) > 0:
                break
            time.sleep(1.0)
        s = get("/api/status")
        assert s["files_total"] >= 1
        assert s["last_summary"], s
        assert s["last_summary"]["completed"] >= 1
        outs = get("/api/files")["outputs"]
        names = [o["name"] for o in outs]
        assert "ui_test.wav" in names

        # Audio-Datei über /files auslieferbar
        raw = urllib.request.urlopen(
            base + "/files/output/ui_test.wav", timeout=30).read()
        assert raw[:4] == b"RIFF"

        # Pfad-Traversal verhindert
        try:
            urllib.request.urlopen(base + "/files/../config/config.json",
                                   timeout=5)
            trav = False
        except Exception:
            trav = True
        assert trav
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def APP_ROOT() -> Path:
    return Path(__file__).resolve().parent.parent
