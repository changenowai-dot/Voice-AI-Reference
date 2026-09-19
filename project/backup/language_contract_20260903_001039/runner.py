"""Job-Runner: stabiles Backend-API für die Desktop-GUI (§6, §16, §32 P2).

``generate_voiceover(text|file, language, voice_id, speed, output_dir)``
als Prozess-Modell: Die GUI startet GENAU EINEN Backend-Prozess
``python app/main.py --job <jobfile>``; dieser liest den Job-Spec (JSON),
führt die GESPERRTE Produktionspipeline aus und schreibt JSONL-Ereignisse
nach stdout (flush-zeilengenau): stage/progress/segment/qc/regen/done/
error. stderr bleibt für technische Diagnose.

Schutzregeln (§3/§12/§13/§24/§29):
- VD-E: Identity-Lock VOR allem; Produktionssamen 52001; allow_design=False
- CustomVoice: Sprecher-Verfügbarkeitsprüfung; kein heimlicher Fallback
- kein paralleler GPU-Prozess (Sperrdatei)
- CUDA-Prüfung: ohne GPU klaren Fehler statt stiller Langsam-Modus (§29)
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .. import paths
from ..logging_setup import get_logger, setup_logging

log = get_logger("jobs")

LOCK_FILE = paths.STATE_DIR / "backend.lock"


# ---------------------------------------------------------------------------
# Job-Spec
# ---------------------------------------------------------------------------
@dataclass
class JobSpec:
    text: str = ""
    text_file: str = ""                # alternativ: Pfad zu .txt
    language: str = "German"           # German | English (§9, manuell)
    voice_id: str = "vd_e"
    speed: float = 1.0
    output_dir: str = ""               # leer = Standard output/
    output_name: str = ""              # leer = aus Eingabe
    formats: list = field(default_factory=lambda: ["wav", "mp3"])
    engine: str = "qwen"               # intern: test_double nur für Tests
    volume_db: float = 0.0
    resume: bool = True                # §19

    @staticmethod
    def from_json_file(path) -> "JobSpec":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        allowed = set(JobSpec.__dataclass_fields__)
        spec = JobSpec(**{k: v for k, v in data.items() if k in allowed})
        if spec.language.capitalize() == "German":
            spec.language = "German"
        elif spec.language.capitalize() == "English":
            spec.language = "English"
        if spec.language not in ("German", "English"):
            raise ValueError(f"Unterstützte Sprachen: German/English "
                             f"(erhalten: {spec.language!r})")
        spec.speed = min(max(float(spec.speed or 1.0), 0.8), 1.2)
        return spec


def emit(event: str, **data) -> None:
    """JSONL-Ereignis an die GUI (stdout, flush)."""
    payload = {"event": event, "ts": round(time.time(), 2)}
    payload.update(data)
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _acquire_lock() -> None:
    paths.STATE_DIR.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.exists():
        try:
            pid = int(LOCK_FILE.read_text().strip() or 0)
        except ValueError:
            pid = 0
        if pid and pid != os.getpid():
            try:
                os.kill(pid, 0)
                raise RuntimeError(
                    "Es läuft bereits ein Backend-Prozess (GPU-Exklusiv, "
                    f"§16). PID {pid}.")
            except (OSError, ProcessLookupError):
                pass                      # toter Lock -> übernehmen
    LOCK_FILE.write_text(str(os.getpid()))


def _release_lock() -> None:
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Produktions-Konfiguration anwenden (§3 LOCKED)
# ---------------------------------------------------------------------------
def apply_production(cfg: dict, production: dict) -> dict:
    """VD-E-Produktionseinstellungen – als geschützte Defaults."""
    from ..tts.sampler import PARAM_SETS
    adv = cfg.setdefault("advanced", {})
    gcfg = cfg.setdefault("german", {})
    if production.get("cache_version"):
        # Cache-Version steuert der Sampler zentral (PARAM_SET_VERSION);
        # Dokumentation hier, damit der Stand nachvollziehbar bleibt.
        gcfg["cache_version"] = production["cache_version"]
    if production.get("expressive_sampling"):
        sp = PARAM_SETS.get(str(production.get("sampling_set", "expressive")),
                            PARAM_SETS["expressive"])
        for k in ("temperature", "top_k", "top_p", "repetition_penalty"):
            adv[k] = sp[k]
        adv["do_sample"] = True
    # Variant BASE (§3): Fachwort-Germanisierung aus, Variation aus,
    # aber Aussprachewörterbuch + Prosody-Support aktiv.
    gcfg["tech_germanization"] = False
    gcfg.setdefault("variation", {})["enabled"] = False
    gcfg["instruct_variant"] = gcfg.get("instruct_variant",
                                        "de_doc_native")
    return cfg


def build_engine(spec: JobSpec, production: dict):
    """Engine-Auswahl nach voice_id (§12: vd_e = eigener Pfad)."""
    from ..voices.registry import VoiceRegistry
    registry = VoiceRegistry()
    entry = registry.get(spec.voice_id)
    if entry is None:
        raise RuntimeError(f"Unbekannte Stimme: {spec.voice_id!r}")

    if entry.backend_mode == "clone":
        # §12/§24: Identity-Lock VOR allem; nie neu designen
        from ..security.identity_lock import assert_vd_e_usable
        status = assert_vd_e_usable(production)
        emit("stage", stage="voice_load", voice="VD-E",
             detail="Identität geprüft: " + status.message)
        if spec.engine == "test_double":
            from ..tts.test_double import TestDoubleCloneEngine
            return TestDoubleCloneEngine(allow_design=False), entry
        from ..hardware.detector import detect_hardware
        from ..tts.qwen_engine import VoiceCloneEngine
        hw = detect_hardware()
        adv_cfg = {}
        try:
            from .. import config as cfgmod
            adv_cfg = cfgmod.load_config().get("advanced", {})
        except Exception:                              # noqa: BLE001
            pass
        return VoiceCloneEngine(
            hw, candidate_id="VD-E",
            description="produktion",  # nur Deskriptor; Referenz ist
                                      # vorhanden und gesperrt
            attn_implementation=adv_cfg.get("attn_implementation") or None,
            allow_design=False), entry

    # CustomVoice (§13): Verfügbarkeit PRÜFEN, kein Fallback
    if spec.engine == "test_double":
        from ..tts.test_double import TestDoubleEngine
        return TestDoubleEngine(), entry
    from ..hardware.detector import detect_hardware, recommend_model_size, \
        recommend_torch_dtype
    from ..tts.qwen_engine import QwenTTSEngine
    hw = detect_hardware()
    if hw.mode == "cpu" and not hw.gpu_name:
        raise RuntimeError(
            "Keine CUDA-fähige GPU gefunden. Die Produktion benötigt CUDA "
            "(§29) – stiller CPU-Modus ist für Produktionsqualität "
            "deaktiviert. GPU/Treiber prüfen und neu starten.")
    from .. import config as cfgmod
    adv = cfgmod.load_config().get("advanced", {})
    engine = QwenTTSEngine(
        hw, model_size=recommend_model_size(
            hw, adv.get("prefer_model_size", "auto")),
        device_hint=None if adv.get("device", "auto") == "auto"
        else adv.get("device"),
        dtype_hint=recommend_torch_dtype(hw),
        attn_implementation=adv.get("attn_implementation") or None)
    return engine, entry


def ensure_speaker_available(engine, entry) -> None:
    """§13: fehlender Sprecher -> klarer Fehler, kein Ersatz."""
    if entry.backend_mode != "customvoice":
        return
    model = getattr(engine, "_model", None) or getattr(engine, "model", None)
    if model is None:
        engine.load()
        model = getattr(engine, "_model", None) or getattr(
            engine, "model", None)
    try:
        supported = {s.lower() for s in
                     (model.get_supported_speakers() or [])}
    except Exception as e:                             # noqa: BLE001
        raise RuntimeError(f"Sprecherliste nicht prüfbar: {e}") from e
    if entry.speaker_name and entry.speaker_name.lower() not in supported:
        raise RuntimeError(
            f"Stimme nicht verfügbar: Sprecher ‚{entry.speaker_name}‘ "
            "fehlt in der installierten Modellversion. Kein automatischer "
            "Ersatz (§13).")


# ---------------------------------------------------------------------------
# Hauptlauf
# ---------------------------------------------------------------------------
def run_job(spec: JobSpec) -> int:
    setup_logging()
    paths.ensure_directories()
    emit("stage", stage="startup", detail="Backend gestartet")
    t0 = time.perf_counter()
    try:
        _acquire_lock()
        # 1) Text beschaffen (§7: PDF/TXT bereits gelesen -> text_file .txt)
        text = spec.text
        if spec.text_file:
            p = Path(spec.text_file)
            if not p.exists():
                raise RuntimeError(f"Eingabedatei fehlt: {p}")
            text = p.read_text(encoding="utf-8", errors="replace")
        if not text or not text.strip():
            raise RuntimeError("Der Text ist leer – nichts zu syntheti-"
                               "sisieren (PDF ohne Text?).")
        emit("stage", stage="text_ready", chars=len(text))

        # 2) Produktion + Konfiguration (§3/§25: GUI kann sie nicht ändern)
        from .. import config as cfgmod
        from ..security.identity_lock import load_production
        production = load_production()
        cfg = cfgmod.load_config()
        if spec.voice_id == "vd_e":
            cfg = apply_production(cfg, production)
        cfg["language"] = spec.language
        cfg["speed"] = spec.speed
        cfg["volume_db"] = spec.volume_db
        cfg["voice"] = {"id": spec.voice_id,
                        "speaker": None,          # setzt build_engine-Kontext
                        "production_seed":
                            production.get("seed")
                            if spec.voice_id == "vd_e" else None}
        if spec.output_dir:
            cfg["output_dir"] = str(Path(spec.output_dir))
        out_dir = Path(spec.output_dir) if spec.output_dir else paths.OUTPUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)

        # 3) Engine + Sprecher (§12/§13/§29)
        emit("stage", stage="voice_load", voice=spec.voice_id)
        engine, entry = build_engine(spec, production)
        if entry.backend_mode == "customvoice":
            cfg["voice"]["speaker"] = entry.speaker_name
        emit("stage", stage="model_load",
             detail="Modell wird geladen (einmalig)")
        engine.load()
        ensure_speaker_available(engine, entry)
        cfg["voice"]["speaker"] = (entry.speaker_name if
                                   entry.backend_mode == "customvoice"
                                   else "VD-E")
        emit("stage", stage="model_ready")

        # 4) Pipeline mit Fortschritts-Events (§17)
        from ..project.pipeline import Pipeline
        from ..ui.progress import ProgressReporter

        class _Emitter(ProgressReporter):
            def update(self, **kw):                   # noqa: D102
                super().update(**kw)
                evt = {"percent": kw.get("overall_percent"),
                       "file": kw.get("current_file"),
                       "segment": kw.get("current_segment"),
                       "segments_total": kw.get("total_segments"),
                       "tts_percent": kw.get("tts_percent"),
                       "qc_percent": kw.get("qc_percent")}
                if kw.get("phase"):
                    evt["stage"] = kw["phase"]
                emit("progress", **{k: v for k, v in evt.items()
                                    if v is not None})

        progress = _Emitter()
        pipe = Pipeline(cfg, engine, progress=progress)
        src = _write_source_text(text, spec, out_dir)
        emit("stage", stage="tts")
        report = pipe.process_file(src)

        # 5) Ergebnis / Report (§21/§22)
        elapsed = time.perf_counter() - t0
        if not report.get("ok"):
            emit("error", message=str(report.get("error",
                                                 "unbekannter Fehler")),
                 detail=json.dumps(report, ensure_ascii=False,
                                   default=str)[:4000], stage="pipeline")
            return 2
        summary = {
            "status": "Erfolgreich",
            "voice": ("VD-E" if spec.voice_id == "vd_e"
                      else entry.display_name),
            "language": spec.language,
            "segments": report.get("segments"),
            "regenerations": report.get("regenerated"),
            "failed": report.get("failed_segments", 0),
            "qc": report.get("avg_score"),
            "duration_s": round(elapsed, 1),
            "wav": report.get("wav"), "mp3": report.get("mp3"),
            "elapsed_s": report.get("elapsed_s"),
            "audio_dur_s": report.get("duration_s"),
        }
        emit("done", summary=summary, wav=report.get("wav"),
             mp3=report.get("mp3"),
             report=_latest_report_md(out_dir))
        _verify_vd_e_hash_post_run(production)        # §33
        return 0
    except Exception as e:                            # noqa: BLE001
        log.exception("Job fehlgeschlagen")
        import traceback
        emit("error", message=str(e),
             detail=traceback.format_exc()[-4000:])
        return 3
    finally:
        _release_lock()


def _write_source_text(text: str, spec: JobSpec, out_dir: Path) -> Path:
    name = spec.output_name or f"gui_{time.strftime('%Y%m%d_%H%M%S')}"
    name = Path(name).stem
    src_dir = paths.INPUT_DIR
    src_dir.mkdir(parents=True, exist_ok=True)
    src = src_dir / f"{name}.txt"
    i = 1
    while src.exists():
        src = src_dir / f"{name}_{i}.txt"
        i += 1
    src.write_text(text, encoding="utf-8")
    return src


def _latest_report_md(out_dir: Path) -> str | None:
    reports = sorted(out_dir.glob("report_*.md"))
    return str(reports[-1]) if reports else None


def _verify_vd_e_hash_post_run(production: dict) -> None:
    """§33: Nach jedem Backend-Test Hash prüfen."""
    from ..security.identity_lock import check_identity
    if str(production.get("reference_sha256", "")):
        status = check_identity(production)
        emit("identity_check", ok=status.ok, level=status.level,
             message=status.message)
