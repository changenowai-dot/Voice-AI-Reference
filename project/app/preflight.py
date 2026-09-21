"""GUI-Preflight (P18): prüft alle Voraussetzungen VOR dem ersten Job.

Im Gegensatz zum früheren "gibt es irgendein Qwen*-Verzeichnis?"-Check
verwendet dieses Modul DIESELBE Modell-Auflösung wie die Runtime
(QwenModelPool + CustomVoice- + VoiceDesign-Modell), so dass eine
fehlgeschlagene Prüfung garantiert auch im echten Lauf fehlschlagen
würde (und umgekehrt).

Die Prüfung wirft KEINE Exception bei fehlendem CUDA/qwen_tts, sondern
gibt einen strukturierten Report zurück; die GUI kann dann eine
verständliche Fehlermeldung anzeigen statt einen kryptischen
Importfehler.
"""
from __future__ import annotations

import importlib
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import paths


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    fatal: bool = False          # wenn True: kein Start möglich
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class PreflightReport:
    ok: bool = True
    fatal_missing: bool = False
    checks: list[CheckResult] = field(default_factory=list)
    python_version: str = ""
    torch_version: str = ""
    cuda_available: bool = False
    cuda_version: str = ""
    gpu_name: str = ""
    ffmpeg_available: bool = False
    models: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)

    def add(self, r: CheckResult) -> None:
        self.checks.append(r)
        if not r.ok:
            self.ok = False
            if r.fatal:
                self.fatal_missing = True

    def summary_lines(self) -> list[str]:
        lines = []
        for c in self.checks:
            mark = "OK " if c.ok else ("!! " if c.fatal else "!  ")
            lines.append(f"[{mark}] {c.name}: {c.detail}")
        return lines


def _try_import(name: str):
    try:
        return importlib.import_module(name)
    except Exception as e:                              # noqa: BLE001
        return e


def run_preflight() -> PreflightReport:
    """Führt alle Preflight-Checks aus und gibt einen Report zurück."""
    rpt = PreflightReport()
    rpt.python_version = sys.version.split()[0]

    # --- Python / tkinter ------------------------------------------------
    try:
        import tkinter  # noqa: F401
        rpt.add(CheckResult("Tkinter (GUI)", True, "verfügbar"))
    except Exception as e:                              # noqa: BLE001
        rpt.add(CheckResult("Tkinter (GUI)", False, str(e), fatal=True))

    # --- Torch -----------------------------------------------------------
    torch = _try_import("torch")
    if isinstance(torch, Exception):
        rpt.add(CheckResult("PyTorch", False, f"nicht installiert: {torch}",
                            fatal=True))
    else:
        rpt.torch_version = getattr(torch, "__version__", "?")
        cuda_ok = bool(getattr(torch, "cuda", None)
                       and torch.cuda.is_available())
        rpt.cuda_available = cuda_ok
        rpt.cuda_version = (torch.version.cuda or "") if cuda_ok else ""
        rpt.gpu_name = (torch.cuda.get_device_name(0) if cuda_ok else "")
        rpt.add(CheckResult(
            "PyTorch", True,
            f"{rpt.torch_version}"
            + (f" · CUDA {rpt.cuda_version} · {rpt.gpu_name}" if cuda_ok
               else " · KEINE CUDA-GPU (Produktion benötigt CUDA)"),
            fatal=not cuda_ok))

    # --- qwen_tts --------------------------------------------------------
    qwen_tts = _try_import("qwen_tts")
    if isinstance(qwen_tts, Exception):
        rpt.add(CheckResult(
            "qwen_tts (Runtime)", False,
            f"nicht installiert: {qwen_tts}", fatal=True))
    else:
        ver = getattr(qwen_tts, "__version__", "(unbekannt)")
        rpt.add(CheckResult("qwen_tts (Runtime)", True, ver))

    # --- FFmpeg ----------------------------------------------------------
    ff = shutil.which("ffmpeg")
    rpt.ffmpeg_available = bool(ff)
    rpt.add(CheckResult(
        "FFmpeg", rpt.ffmpeg_available,
        ff if ff else "nicht im PATH (install.ps1 ausführen)",
        fatal=not rpt.ffmpeg_available))

    # --- VD-E Golden Reference -------------------------------------------
    vd_e = paths.ROOT / "VD-E_GOLDEN_REFERENCE" / "VD-E.wav"
    if vd_e.exists():
        import hashlib
        h = hashlib.sha256(vd_e.read_bytes()).hexdigest()
        expected = ("b156c02a60a873ad95fc92390c4a136c85308b20188373cd734bee5e5e5f2025")
        if h == expected:
            rpt.add(CheckResult("VD-E Golden Reference", True,
                                "SHA-256 OK"))
        else:
            rpt.add(CheckResult(
                "VD-E Golden Reference", False,
                f"SHA weicht ab! Erwartet {expected[:16]}…, erhalten "
                f"{h[:16]}… – App ist GESPERRT.", fatal=True))
    else:
        rpt.add(CheckResult("VD-E Golden Reference", False,
                            f"Datei fehlt: {vd_e}", fatal=True))

    # --- Modelle ---------------------------------------------------------
    # Der Preflight muss DENSELBEN Pfad verwenden wie die Runtime UND bei
    # CUDA-Verfügbarkeit auch wirklich Initialisierung + .load() des
    # BASE-Modells durchführen (ein reiner Pfad-Check lässt Fälle wie
    # FINAL_MODEL_NOT_READY durch).
    model_status: dict[str, Any] = {}
    if not isinstance(torch, Exception) and not isinstance(qwen_tts, Exception):
        try:
            from .tts.model_pool import QwenModelPool
            from .hardware.detector import detect_hardware
            hw = detect_hardware()
            pool = QwenModelPool(hw,
                                 dtype_hint=("bfloat16" if rpt.cuda_available else "float32"),
                                 attn_implementation="sdpa")
            # (1) Pfade auflösen
            for name in ("base", "customvoice", "voicedesign"):
                try:
                    p = pool._resolve_model_path(pool.MODEL_REPOS[name])
                    from pathlib import Path as _P
                    pp = _P(p)
                    has_model = ((pp/"model.safetensors").is_file()
                                 or any(pp.glob("*.safetensors")))
                    has_cfg = (pp/"config.json").is_file()
                    has_tok = ((pp/"tokenizer.json").is_file()
                               or (pp/"tokenizer_config.json").is_file())
                    if not has_model:
                        raise FileNotFoundError(f"Keine Modelldatei in {p}")
                    if not has_cfg:
                        raise FileNotFoundError(f"Keine config.json in {p}")
                    if not has_tok:
                        raise FileNotFoundError(f"Keine Tokenizer-Datei in {p}")
                    model_status[name] = {"path": p, "found": True}
                    rpt.add(CheckResult(f"Modell {name} (Pfad)", True,
                                        f"{Path(p).name}"))
                except FileNotFoundError as fnf:
                    model_status[name] = {"path": None, "found": False,
                                          "detail": str(fnf)}
                    fatal = (name == "base")
                    rpt.add(CheckResult(f"Modell {name}", False, str(fnf),
                                        fatal=fatal))
            # (2) Echter Modell-Lade-Test wenn CUDA + Base-Pfad OK
            if rpt.cuda_available and model_status.get("base", {}).get("found"):
                import threading, time as _t
                load_err: list = []
                def _do_load():
                    try:
                        pool.get("base")
                    except Exception as e:                  # noqa: BLE001
                        load_err.append(e)
                th = threading.Thread(target=_do_load, daemon=True)
                t0 = _t.time()
                th.start()
                th.join(180)     # max. 180s für Modell-Lade-Test
                dt = _t.time() - t0
                if th.is_alive():
                    rpt.add(CheckResult(
                        "Modell base (Load-Test)", False,
                        f"Timeout nach 180s beim Laden – Modell hängt.",
                        fatal=True))
                    model_status["base_load_test"] = {"ok": False,
                        "error": "timeout after 180s"}
                elif load_err:
                    rpt.add(CheckResult(
                        "Modell base (Load-Test)", False,
                        f"Fehler bei Initialisierung: "
                        f"{type(load_err[0]).__name__}: {load_err[0]}",
                        fatal=True))
                    model_status["base_load_test"] = {"ok": False,
                        "error": str(load_err[0])}
                else:
                    rpt.add(CheckResult(
                        "Modell base (Load-Test)", True,
                        f"OK ({dt:.1f}s) – Tokenizer + Modell geladen"))
                    model_status["base_load_test"] = {"ok": True,
                        "time_s": round(dt, 2)}
                    try:
                        pool.unload()
                    except Exception:
                        pass
        except Exception as e:                          # noqa: BLE001
            rpt.add(CheckResult("Modellprüfung", False, str(e), fatal=False))
    else:
        for name in ("base", "customvoice", "voicedesign"):
            model_status[name] = {"path": None, "found": False,
                                  "detail": "qwen_tts oder torch nicht installiert"}
    rpt.models = model_status

    # --- Reference-Bundles (Bundled + Cache + VD-E Golden) ----------------
    # Versuche zuerst auto-materialization (idempotent), damit ein frischer
    # Checkout nach dem Setup ohne GPU bereits über alle Release-Bundles
    # im Cache verfügt.
    missing_production: list[str] = []
    try:
        from .voices.registry import VoiceRegistry, tier_for
        from .tts.reference_bundle import (
            bundled_bundle_path, default_bundle_path,
            ensure_bundle_materialized, load_bundle, manifest_path_for,
        )
        reg = VoiceRegistry()
        production_ids = [vid for vid, prof in reg._profiles.items()
                          if tier_for(prof) == "ACTIVE" and vid != "vd_e"
                          and prof.get("backend_mode") == "clone"]
        materialized = 0
        invalid = 0
        for vid in production_ids:
            # Versuche Materialisierung aus gebündeltem Ordner.
            mat = ensure_bundle_materialized(vid)
            if mat is not None and mat.parent == paths.VOICE_REFS_DIR:
                materialized += 1
            # Prüfe WAV + Manifest im Cache ODER im Bundle-Ordner.
            candidates = [default_bundle_path(vid), bundled_bundle_path(vid)]
            found = None
            for c in candidates:
                if c.exists():
                    found = c; break
            if found is None:
                missing_production.append(vid); continue
            mp = manifest_path_for(found)
            if not mp.exists():
                missing_production.append(vid); continue
            bundle = load_bundle(found, voice_id=vid)
            if bundle is None:
                invalid += 1
        # VD-E separat
        ensure_bundle_materialized("vd_e")
        vde_cache = default_bundle_path("vd_e")
        vde_bundled = bundled_bundle_path("vd_e")
        vde_ok = vde_cache.exists() or vde_bundled.exists() or paths.VD_E_GOLDEN_REF_PATH.exists()
        rpt.data["reference_bundles"] = {
            "production_count": len(production_ids),
            "materialized": materialized,
            "missing": missing_production,
            "invalid": invalid,
            "vde_ok": vde_ok,
            "bundled_dir": str(paths.BUNDLED_REF_DIR),
            "cache_dir": str(paths.VOICE_REFS_DIR),
        }
        detail = (f"{len(production_ids)} Production-Stimmen · "
                  f"Cache: {paths.VOICE_REFS_DIR}")
        if materialized:
            detail += f" · {materialized} aus Bundle kopiert"
        if missing_production:
            detail += f" · FEHLEND: {', '.join(missing_production[:4])}"
            detail += " …" if len(missing_production) > 4 else ""
            rpt.add(CheckResult(
                "Referenz-Bundles", False, detail, fatal=False))
        else:
            rpt.add(CheckResult("Referenz-Bundles", True, detail))
        if not vde_ok:
            rpt.add(CheckResult(
                "VD-E Runtime-Referenz", False,
                f"Weder Cache noch Golden Reference vorhanden "
                f"({paths.VD_E_GOLDEN_REF_PATH})", fatal=True))
        else:
            rpt.add(CheckResult(
                "VD-E Runtime-Referenz", True,
                "verfügbar (Golden Reference gebootstrappt oder im Cache)"))
    except Exception as e:                              # noqa: BLE001
        rpt.add(CheckResult("Referenz-Bundles", False,
                            f"Prüfung fehlgeschlagen: {e}", fatal=False))
    return rpt
