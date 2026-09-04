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
    # v2 (§8/§10): optionales Marker-Splitting + Ausgabemodus
    splitting_enabled: bool = False    # aus = exakt bisheriges Verhalten
    output_mode: str = "full"          # full | parts | parts_plus_full

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
        if spec.output_mode not in ("full", "parts", "parts_plus_full"):
            raise ValueError(f"Ungültiger Ausgabemodus: "
                             f"{spec.output_mode!r}")
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

        # v2 (§8–§12): optionales Marker-Splitting – NIE zeitbasiert
        from ..text.script_split import (FULLSCRIPT_SUFFIX, count_markers,
                                         part_name, split_manuscript)
        plan_use_split = bool(spec.splitting_enabled) and \
            count_markers(text) > 0
        if plan_use_split:
            sections = split_manuscript(text)
            mode = spec.output_mode
            if mode == "full":
                # Splitting an + Modus A: hochstufig auf C (dokumentiert)
                mode = "parts_plus_full"
                emit("stage", stage="split",
                     detail=f"Splitting aktiv, Modus A -> C "
                            f"({len(sections)} Parts + FullScript)")
            emit("stage", stage="split",
                 detail=f"{len(sections)} Abschnitte erkannt "
                        f"(Modus {mode})")
        else:
            sections = [text]
            mode = "full"

        base_name = (spec.output_name or
                     f"gui_{time.strftime('%Y%m%d_%H%M%S')}").stem \
            if hasattr(spec.output_name, "stem") else \
            Path(spec.output_name or
                 f"gui_{time.strftime('%Y%m%d_%H%M%S')}").stem

        part_reports = []
        failed_parts: list[str] = []
        for i, section in enumerate(sections, 1):
            if plan_use_split:
                emit("stage", stage="part", part=i, parts=len(sections))
                name = part_name(base_name, i)
            else:
                name = base_name
            src = _write_source_text(section, spec, out_dir, name=name)
            emit("stage", stage="tts",
                 detail=f"Abschnitt {i}/{len(sections)}" if plan_use_split
                 else "")
            report = pipe.process_file(src)
            if not report.get("ok"):
                failed_parts.append(f"Part_{i:03d}: "
                                    + str(report.get("error",
                                                     "Fehler")))
                emit("error",
                     message=f"Abschnitt {i} fehlgeschlagen: "
                             f"{report.get('error', '')}",
                     detail=json.dumps(report, ensure_ascii=False,
                                       default=str)[:2000],
                     stage="pipeline", part=i, parts=len(sections))
                continue
            part_reports.append(report)

        if not part_reports:
            emit("error", message="Alle Abschnitte fehlgeschlagen.",
                 stage="pipeline")
            return 2

        # v2 (§10 MODE C): FullScript aus PART-Materialien (kein Re-TTS)
        full_wav = full_mp3 = None
        if plan_use_split and mode == "parts_plus_full":
            emit("stage", stage="concat",
                 detail="FullScript wird aus den Parts zusammengefügt")
            from ..audio.concat import concat_wavs, encode_mp3
            from ..audio.io import read_wav
            part_wavs = [Path(r["wav"]) for r in part_reports]
            full_wav = out_dir / f"{base_name}_{FULLSCRIPT_SUFFIX}.wav"
            cres = concat_wavs(part_wavs, full_wav,
                               bit_depth=int(adv_cfg_bit_depth(cfg)))
            if not cres.get("ok"):
                emit("error",
                     message="FullScript-Zusammenfügen fehlgeschlagen: "
                             f"{cres.get('error', '')}",
                     stage="concat")
                return 2
            full_mp3 = full_wav.with_suffix(".mp3")
            if not encode_mp3(full_wav, full_mp3):
                full_mp3 = None
            emit("stage", stage="concat_done",
                 detail=f"FullScript: {cres.get('seconds')} s "
                        f"({cres.get('method')})")

        # 5) Ergebnis / Report (§21/§22)
        elapsed = time.perf_counter() - t0
        last = part_reports[-1]
        seg_total = sum(int(r.get("segments") or 0) for r in part_reports)
        regen_total = sum(int(r.get("regenerated") or 0)
                          for r in part_reports)
        failed_total = sum(int(r.get("failed_segments") or 0)
                           for r in part_reports) + len(failed_parts)
        qc_values = [r.get("avg_score") for r in part_reports
                     if r.get("avg_score") is not None]
        import numpy as _np
        summary = {
            "status": "Erfolgreich" if not failed_parts else
                      "Teilweise fehlerhaft",
            "voice": ("VD-E" if spec.voice_id == "vd_e"
                      else entry.display_name),
            "language": spec.language,
            "segments": seg_total,
            "regenerations": regen_total,
            "failed": failed_total,
            "failed_parts": failed_parts,
            "qc": round(float(_np.mean(qc_values)), 1) if qc_values
            else None,
            "duration_s": round(elapsed, 1),
            "wav": last.get("wav"), "mp3": last.get("mp3"),
            "elapsed_s": round(elapsed, 1),
            "audio_dur_s": sum(float(r.get("duration_s") or 0)
                               for r in part_reports),
            "parts": ([{"wav": r.get("wav"), "mp3": r.get("mp3"),
                        "segments": r.get("segments")}
                       for r in part_reports] if plan_use_split else None),
            "fullscript_wav": str(full_wav) if full_wav else None,
            "fullscript_mp3": str(full_mp3) if full_mp3 else None,
            "output_mode": mode,
        }
        emit("done", summary=summary, wav=summary["wav"],
             mp3=summary["mp3"],
             parts=summary["parts"], fullscript=str(full_wav) if full_wav
             else None,
             report=_latest_report_md(out_dir))
        _verify_vd_e_hash_post_run(production)        # §33
        return 0 if not failed_parts else 1
    except Exception as e:                            # noqa: BLE001
        log.exception("Job fehlgeschlagen")
        import traceback
        emit("error", message=str(e),
             detail=traceback.format_exc()[-4000:])
        return 3
    finally:
        _release_lock()


def adv_cfg_bit_depth(cfg: dict) -> int:
    return int((cfg.get("advanced", {}) or {}).get("wav_bit_depth", 24))


def _write_source_text(text: str, spec: JobSpec, out_dir: Path,
                       name: str = "") -> Path:
    name = name or spec.output_name or \
        f"gui_{time.strftime('%Y%m%d_%H%M%S')}"
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
