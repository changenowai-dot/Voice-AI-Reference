"""Lokale Web-Oberfläche (Anforderung 28–31).

Schlanker stdlib-HTTP-Server (keine Zusatzabhängigkeiten) mit JSON-API
und statischem Frontend. Läuft nur auf 127.0.0.1 (lokal, Datenschutz).
"""
from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from .. import config as cfgmod
from .. import paths
from ..batch.runner import BatchRunner, list_input_files
from ..cache.manager import CacheManager
from ..hardware.detector import detect_hardware
from ..logging_setup import get_logger, setup_logging
from ..project.pipeline import Pipeline
from ..benchmark.phase2_ab import (apply_pick_or_candidate, blind_status,
                                   run_pause_probe, run_phase2,
                                   save_blind_pick)
from ..benchmark.phase3 import (apply_phase3_pick, phase3_status,
                                run_phase3, save_phase3_pick)
from ..pronunciation import PronunciationDictionary
from ..tts.sampler import PARAM_SET_VERSION
from ..ui.progress import ProgressReporter
from ..utils import read_json, write_json

log = get_logger("ui")

STATIC_DIR = Path(__file__).parent / "static"


class AppContext:
    """Geteilter Zustand der Anwendung (Engine, Threads, Fortschritt)."""

    def __init__(self, engine_name: str = "qwen"):
        self.engine_name = engine_name
        self.progress = ProgressReporter()
        self._hw = None
        self._engine = None
        self._engine_lock = threading.Lock()
        self._batch_thread: threading.Thread | None = None
        self._bench_thread: threading.Thread | None = None

    # -- Hardware (cachebar) -------------------------------------------------
    @property
    def hw(self):
        if self._hw is None:
            self._hw = detect_hardware()
        return self._hw

    def refresh_hardware(self):
        self._hw = detect_hardware()
        return self._hw

    # -- Engine ---------------------------------------------------------------
    def get_engine(self):
        with self._engine_lock:
            if self._engine is None:
                self.progress.event("Qwen3-TTS-Modell wird geladen "
                                    "(einmalig, ca. 10-60 s) …")
                from ..hardware.detector import (recommend_model_size,
                                                 recommend_torch_dtype)
                cfgd = cfgmod.load_config()
                adv = cfgd.get("advanced", {})
                size = adv.get("prefer_model_size", "auto")
                model_size = recommend_model_size(self.hw, size)
                if self.engine_name == "test_double":
                    from ..tts.test_double import TestDoubleEngine
                    self._engine = TestDoubleEngine()
                else:
                    from .. import config as _cfg
                    gcfg = _cfg.load_config().get("german", {}) or {}
                    if gcfg.get("engine_mode") == "voicedesign" and                             (gcfg.get("voicedesign") or {}).get(
                                "candidate_id"):
                        from ..tts.qwen_engine import VoiceCloneEngine
                        vd = gcfg["voicedesign"]
                        self._engine = VoiceCloneEngine(
                            hw=self.hw, candidate_id=vd["candidate_id"],
                            description=vd.get("description", ""),
                            attn_implementation=adv.get(
                                "attn_implementation") or None)
                    else:
                        from ..tts.qwen_engine import QwenTTSEngine
                        device = adv.get("device", "auto")
                        attn = adv.get("attn_implementation") or None
                        self._engine = QwenTTSEngine(
                            hw=self.hw, model_size=model_size,
                            device_hint=None if device == "auto" else device,
                            dtype_hint=recommend_torch_dtype(self.hw),
                            attn_implementation=attn)
                self._engine.load()
            return self._engine

    def reset_engine(self):
        with self._engine_lock:
            if self._engine is not None:
                try:
                    self._engine.unload()
                except Exception:
                    pass
                self._engine = None

    # -- Batch ------------------------------------------------------------------
    def start_batch(self, files: list[Path] | None = None) -> bool:
        if self.progress.snapshot().get("running"):
            return False

        def _factory():
            return Pipeline(cfgmod.load_config(), self.get_engine(),
                            progress=self.progress)

        runner = BatchRunner(_factory, progress=self.progress)

        def _run():
            try:
                summary = runner.run(files)
                self.progress.update(last_summary=summary)
            except Exception as e:
                log.exception("Batch abgebrochen: %s", e)
                self.progress.update(running=False, last_error=str(e))
        self.progress.reset()
        self._batch_thread = threading.Thread(target=_run, daemon=True,
                                              name="batch")
        self._batch_thread.start()
        return True

    def start_benchmark(self, kind: str, quick: bool = False) -> bool:
        if self.progress.snapshot().get("running"):
            return False

        def _run():
            self.progress.update(running=True, phase=f"benchmark_{kind}")
            try:
                if kind == "system":
                    from ..benchmark.system import run_system_benchmark
                    rep = run_system_benchmark(lambda size: self.get_engine()
                                               if self.engine_name != "qwen"
                                               else self._engine_for(size),
                                               quick=quick, hw=self.hw)
                    self.progress.update(phase="benchmark_done",
                                         last_summary={"benchmark": "system",
                                                       "ok": rep["ok"]})
                elif kind == "voices":
                    from ..voices.benchmark import run_voice_benchmark
                    rep = run_voice_benchmark(self.get_engine(), quick=quick)
                    self.progress.update(phase="benchmark_done",
                                         last_summary={"benchmark": "voices",
                                                       "ok": True})
                elif kind == "german_baseline":
                    from ..benchmark.german_ab import ensure_baseline
                    rep = ensure_baseline(self.get_engine())
                    self.progress.update(
                        phase="benchmark_done",
                        last_summary={"benchmark": "german_baseline",
                                      "ok": True,
                                      "de_score": rep.get("german_overall")})
                elif kind == "german_ab":
                    from ..benchmark.german_ab import run_ab
                    rep = run_ab(self.get_engine(), quick=quick)
                    self.progress.update(
                        phase="benchmark_done",
                        last_summary={"benchmark": "german_ab", "ok": True,
                                      "de_score": rep["winner"].get(
                                          "german_overall")})
                elif kind == "german_speakers":
                    from ..voices.benchmark import (
                        run_german_speaker_benchmark)
                    rep = run_german_speaker_benchmark(self.get_engine(),
                                                       quick=quick)
                    self.progress.update(
                        phase="benchmark_done",
                        last_summary={
                            "benchmark": "german_speakers", "ok": True,
                            "best": rep.get("best_german_narrator")})
            except Exception as e:
                log.exception("Benchmark fehlgeschlagen: %s", e)
                self.progress.update(last_error=str(e))
            finally:
                self.progress.update(running=False)
        self._bench_thread = threading.Thread(target=_run, daemon=True,
                                              name="benchmark")
        self._bench_thread.start()
        return True

    def _engine_for(self, size: str):
        """Engine in gewünschter Modellgröße für den System-Benchmark."""
        with self._engine_lock:
            cur = self._engine
            info = cur.info() if cur else {}
            if info.get("model_size") == size:
                return cur
            if cur is not None:
                try:
                    cur.unload()
                except Exception:
                    pass
                self._engine = None
            from ..tts.qwen_engine import QwenTTSEngine
            adv = cfgmod.load_config().get("advanced", {})
            eng = QwenTTSEngine(hw=self.hw, model_size=size,
                                attn_implementation=adv.get(
                                    "attn_implementation") or None)
            eng.load()
            self._engine = eng
            return eng


CTX = AppContext()


class Handler(BaseHTTPRequestHandler):
    server_version = "VoiceOverApp/1.0"

    def log_message(self, fmt, *args):     # ruhiger Server
        log.debug("%s %s", self.address_string(), fmt % args)

    # ----------------------------------------------------------- Routing ----
    def _send_json(self, obj, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, mime: str) -> None:
        try:
            body = path.read_bytes()
        except OSError:
            self._send_json({"error": "nicht gefunden"}, 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        route = url.path
        try:
            if route in ("/", "/index.html"):
                self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            elif route.endswith(".css"):
                self._send_file(STATIC_DIR / "style.css", "text/css; charset=utf-8")
            elif route.endswith(".js"):
                self._send_file(STATIC_DIR / "app.js", "text/javascript; charset=utf-8")
            elif route == "/api/status":
                self._api_status()
            elif route == "/api/config":
                self._api_get_config()
            elif route == "/api/pronunciation":
                self._api_get_pronunciation()
            elif route == "/api/cache":
                self._send_json(CacheManager(enabled=False).stats())
            elif route == "/api/phase2/status":
                self._send_json(blind_status())
            elif route == "/api/phase3/status":
                self._send_json(phase3_status())
            elif route == "/api/files":
                self._api_files()
            elif route.startswith("/files/"):
                self._api_serve_file(route)
            else:
                self._send_json({"error": "unbekannte Route"}, 404)
        except BrokenPipeError:
            pass
        except Exception as e:                     # noqa: BLE001
            log.exception("GET %s fehlgeschlagen", route)
            self._send_json({"error": str(e)}, 500)

    def do_POST(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        route = url.path
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            self._send_json({"error": "ungültiger Request-Body"}, 400)
            return
        try:
            if route == "/api/start":
                self._api_start(data)
            elif route == "/api/stop":
                CTX.progress.request_cancel()
                self._send_json({"ok": True, "message": "Abbruch angefordert …"})
            elif route == "/api/config":
                self._api_set_config(data)
            elif route == "/api/pronunciation":
                self._api_post_pronunciation(data)
            elif route == "/api/cache/clear":
                self._api_cache_clear(data)
            elif route == "/api/upload":
                self._api_upload(data)
            elif route == "/api/phase2/run":
                self._api_phase2_run(data)
            elif route == "/api/phase3/run":
                self._api_phase3_run(data)
            elif route == "/api/phase3/blind_pick":
                try:
                    st = save_phase3_pick(data.get("letter", ""))
                    self._send_json({"ok": True, "status": st})
                except ValueError as e:
                    self._send_json({"error": str(e)}, 400)
            elif route == "/api/phase3/apply":
                try:
                    res = apply_phase3_pick()
                    CTX.reset_engine()
                    self._send_json(res)
                except ValueError as e:
                    self._send_json({"error": str(e)}, 400)
            elif route == "/api/phase2/blind_pick":
                try:
                    status = save_blind_pick(data.get("letter", ""))
                    self._send_json({"ok": True, "status": status})
                except ValueError as e:
                    self._send_json({"error": str(e)}, 400)
            elif route == "/api/phase2/apply":
                try:
                    res = apply_pick_or_candidate(data.get("candidate_id"))
                    CTX.reset_engine()
                    self._send_json(res)
                except ValueError as e:
                    self._send_json({"error": str(e)}, 400)
            elif route == "/api/benchmark":
                ok = CTX.start_benchmark(data.get("type", "system"),
                                         quick=bool(data.get("quick")))
                self._send_json({"ok": ok})
            elif route == "/api/hardware/refresh":
                CTX.refresh_hardware()
                self._send_json(CTX.hw.to_dict())
            else:
                self._send_json({"error": "unbekannte Route"}, 404)
        except Exception as e:                     # noqa: BLE001
            log.exception("POST %s fehlgeschlagen", route)
            self._send_json({"error": str(e)}, 500)

    # ------------------------------------------------------------- APIs ----
    def _api_status(self) -> None:
        snap = CTX.progress.snapshot()
        snap["cache"] = CacheManager(enabled=False).stats()
        snap["engine"] = (CTX._engine.info() if CTX._engine else None)
        snap["model_size_effective"] = (
            CTX._engine.info().get("model_size") if CTX._engine else None)
        from ..audio.ffmpeg import ffmpeg_available
        snap["ffmpeg"] = ffmpeg_available()
        bench = read_json(paths.BENCHMARK_DIR / "system_benchmark.json", None)
        snap["system_benchmark"] = {
            "ok": (bench or {}).get("ok"),
            "timestamp": (bench or {}).get("timestamp"),
            "mode": ((bench or {}).get("hardware") or {}).get("mode"),
        } if bench else None
        self._send_json(snap)

    def _api_get_config(self) -> None:
        cfg = cfgmod.load_config()
        from ..prosody.presets import load_presets
        from ..voices.profiles import (DEFAULT_BEST_NARRATOR_ID,
                                       DEFAULT_BEST_NARRATOR_LABEL, PROFILES)
        self._send_json({
            "config": cfg,
            "presets": load_presets(),
            "profiles": [{"id": p.id, "label": p.label, "speaker": p.speaker,
                          "description": p.description, "gender": p.gender}
                         for p in PROFILES.values()],
            "default_profile": DEFAULT_BEST_NARRATOR_ID,
            "default_label": DEFAULT_BEST_NARRATOR_LABEL,
            "hardware": CTX.hw.to_dict(),
            "param_set_version": PARAM_SET_VERSION,
        })

    def _apply_config_patch(self, data: dict) -> dict:
        allowed_top = {"language", "voice_profile", "preset", "speed",
                       "emotion", "intensity", "volume_db", "pause_style",
                       "advanced", "ui"}
        patch = {k: v for k, v in data.items() if k in allowed_top}
        cfg = cfgmod.update_config(patch)
        CTX.reset_engine()
        return cfg

    def _api_set_config(self, data: dict) -> None:
        if CTX.progress.snapshot().get("running"):
            self._send_json({"error": "Läuft noch – bitte warten oder abbrechen"},
                            409)
            return
        cfg = self._apply_config_patch(data)
        self._send_json({"ok": True, "config": cfg})

    def _api_files(self) -> None:
        files = list_input_files()
        self._send_json({
            "input_dir": str(paths.INPUT_DIR),
            "output_dir": str(paths.OUTPUT_DIR),
            "files": [{"name": f.name, "size": f.stat().st_size}
                      for f in files],
            "outputs": [{"name": f.name, "size": f.stat().st_size}
                        for f in sorted(paths.OUTPUT_DIR.glob("*"))
                        if f.is_file()],
        })

    def _api_start(self, data: dict) -> None:
        if CTX.progress.snapshot().get("running"):
            self._send_json({"ok": False, "error": "Es läuft bereits ein Auftrag."},
                            409)
            return
        if data:
            self._apply_config_patch(data)
        files = None
        if data.get("files"):
            files = [paths.INPUT_DIR / f for f in data["files"]
                     if (paths.INPUT_DIR / f).exists()]
        ok = CTX.start_batch(files)
        self._send_json({"ok": ok})

    def _api_phase2_run(self, data: dict) -> None:
        if CTX.progress.snapshot().get("running"):
            self._send_json({"ok": False,
                             "error": "Es läuft bereits ein Auftrag."}, 409)
            return
        CTX.progress.update(running=True, phase="phase2_benchmark")

        def _run():
            try:
                if data.get("probe") == "pauses":
                    out = run_pause_probe(_phase2_studio())
                    CTX.progress.update(
                        phase="benchmark_done",
                        last_summary={"benchmark": "phase2_pauses", "ok": True,
                                      "strategies": list(out)})
                else:
                    rep = run_phase2(_phase2_studio(), quick=bool(
                        data.get("quick")))
                    ok = all(not c.get("error")
                             for c in rep["candidates"]) or True
                    CTX.progress.update(
                        phase="benchmark_done",
                        last_summary={"benchmark": "phase2", "ok": ok,
                                      "recommended":
                                          rep["recommendation"][
                                              "recommended"]})
            except Exception as e:                    # noqa: BLE001
                log.exception("Phase-2-Lauf fehlgeschlagen")
                CTX.progress.update(last_error=str(e))
            finally:
                CTX.progress.update(running=False)

        def _phase2_studio():
            if CTX.engine_name == "test_double":
                from ..tts.voice_studio import TestDoubleVoiceStudio
                return TestDoubleVoiceStudio()
            from ..hardware.detector import recommend_torch_dtype
            from ..tts.model_pool import QwenModelPool
            from ..tts.voice_studio import QwenVoiceStudio
            adv = cfgmod.load_config().get("advanced", {})
            pool = QwenModelPool(
                CTX.hw, attn_implementation=adv.get(
                    "attn_implementation") or None)
            return QwenVoiceStudio(pool)

        threading.Thread(target=_run, daemon=True, name="phase2").start()
        self._send_json({"ok": True})

    def _api_phase3_run(self, data: dict) -> None:
        if CTX.progress.snapshot().get("running"):
            self._send_json({"ok": False,
                             "error": "Es läuft bereits ein Auftrag."}, 409)
            return
        CTX.progress.update(running=True, phase="phase3_benchmark")

        def _run():
            try:
                run_phase3(_phase3_studio(), quick=bool(data.get("quick")))
                CTX.progress.update(phase="benchmark_done",
                                    last_summary={
                                        "benchmark": "phase3", "ok": True})
            except Exception as e:                    # noqa: BLE001
                log.exception("Phase-3-Lauf fehlgeschlagen")
                CTX.progress.update(last_error=str(e))
            finally:
                CTX.progress.update(running=False)

        def _phase3_studio():
            if CTX.engine_name == "test_double":
                from ..tts.voice_studio import TestDoubleVoiceStudio
                return TestDoubleVoiceStudio()
            from ..tts.model_pool import QwenModelPool
            from ..tts.voice_studio import QwenVoiceStudio
            adv = cfgmod.load_config().get("advanced", {})
            pool = QwenModelPool(CTX.hw, attn_implementation=adv.get(
                "attn_implementation") or None)
            return QwenVoiceStudio(pool)

        threading.Thread(target=_run, daemon=True, name="phase3").start()
        self._send_json({"ok": True})

    def _api_get_pronunciation(self) -> None:
        d = PronunciationDictionary()
        self._send_json({
            "user": d.user_entries(),
            "builtin_count": len(d.builtin_entries()),
            "file": str(paths.PRONUNCIATION_FILE),
        })

    def _api_post_pronunciation(self, data: dict) -> None:
        d = PronunciationDictionary()
        action = data.get("action")
        if action == "add":
            d.add_entry(data["term"], data["value"],
                        data.get("language", "both"))
        elif action == "delete":
            ok = d.delete_entry(data["term"])
            self._send_json({"ok": ok})
            return
        elif action == "clear":
            if not data.get("confirm"):
                self._send_json({"error": "confirm=true erforderlich"}, 400)
                return
            d.clear_all()
        elif action == "import":
            count = d.import_user(data.get("entries", {}),
                                  replace=bool(data.get("replace")))
            self._send_json({"ok": True, "imported": count})
            return
        else:
            self._send_json({"error": "unbekannte Aktion"}, 400)
            return
        self._send_json({"ok": True, "user": d.user_entries()})

    def _api_cache_clear(self, data: dict) -> None:
        cm = CacheManager(enabled=True)
        scope = data.get("scope", "")
        if not data.get("confirm"):
            self._send_json({"error": "Sicherheitsabfrage: confirm=true nötig"},
                            400)
            return
        if scope == "all":
            n = cm.clear_all()
            self._send_json({"ok": True, "removed": n})
        elif scope == "failed":
            n = cm.clear_failed()
            self._send_json({"ok": True, "removed": n})
        elif scope == "project":
            n = cm.clear_project(data.get("project_id", ""))
            self._send_json({"ok": True, "removed": n})
        else:
            self._send_json({"error": "scope: all|failed|project"}, 400)

    def _api_upload(self, data: dict) -> None:
        name = Path(data.get("name", "upload.txt")).name
        if not name.lower().endswith(".txt"):
            name += ".txt"
        content = data.get("content", "")
        if not isinstance(content, str) or not content.strip():
            self._send_json({"error": "leere Datei"}, 400)
            return
        paths.INPUT_DIR.mkdir(parents=True, exist_ok=True)
        target = paths.INPUT_DIR / name
        i = 1
        while target.exists():
            target = paths.INPUT_DIR / f"{Path(name).stem}_{i}.txt"
            i += 1
        target.write_text(content, encoding="utf-8")
        log.info("Upload: %s (%d Zeichen)", target.name, len(content))
        self._send_json({"ok": True, "name": target.name})

    def _api_serve_file(self, route: str) -> None:
        rel = route[len("/files/"):]
        base = paths.ROOT.resolve()
        target = (base / rel).resolve()
        if not str(target).startswith(str(base)):
            self._send_json({"error": "Pfad nicht erlaubt"}, 403)
            return
        if not target.is_file():
            self._send_json({"error": "nicht gefunden"}, 404)
            return
        mime = ("audio/wav" if target.suffix == ".wav"
                else "audio/mpeg" if target.suffix == ".mp3"
                else "text/plain; charset=utf-8" if target.suffix in (".md", ".json", ".txt")
                else "application/octet-stream")
        self._send_file(target, mime)


def run_server(port: int = 8750, open_browser: bool = True,
               engine_name: str = "qwen") -> None:
    global CTX
    CTX = AppContext(engine_name=engine_name)
    setup_logging()
    paths.ensure_directories()
    cfgmod.write_default_config_if_missing()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    log.info("Oberfläche: %s", url)
    print(f"\n  VoiceOverApp läuft unter {url}\n")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("Server beendet (Strg+C)")
    finally:
        httpd.server_close()
