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
    # Nur prüfen, wenn wir qwen_tts+torch haben; sonst würden Import-
    # fehler die Prüfung nutzlos machen.
    model_status: dict[str, Any] = {}
    if not isinstance(torch, Exception) and not isinstance(qwen_tts, Exception):
        try:
            from .tts.model_pool import QwenModelPool
            # leerer hw dummy für reine Pfadprüfung
            class _HW:
                mode = "gpu" if rpt.cuda_available else "cpu"
                device_capability = (8, 9)
            pool = QwenModelPool(_HW(), dtype_hint="bfloat16",
                                 attn_implementation="sdpa")
            for name in ("customvoice", "base", "voicedesign"):
                try:
                    p = pool._resolve_model_path(pool.MODEL_REPOS[name])
                    model_status[name] = {"path": p, "found": True}
                    rpt.add(CheckResult(
                        f"Modell {name}", True, p))
                except FileNotFoundError as fnf:
                    # Extrahiere die vom Loader erwarteten Pfade
                    msg = str(fnf)
                    model_status[name] = {"path": None, "found": False,
                                          "detail": msg}
                    rpt.add(CheckResult(
                        f"Modell {name}", False, msg,
                        fatal=(name in ("customvoice",)) and not rpt.fatal_missing))
        except Exception as e:                          # noqa: BLE001
            rpt.add(CheckResult("Modellprüfung", False, str(e),
                                fatal=False))
    else:
        # Falls qwen_tts fehlt, überspringen (haben wir schon als fatal
        # markiert).
        for name in ("customvoice", "base", "voicedesign"):
            model_status[name] = {"path": None, "found": False,
                                  "detail": "qwen_tts nicht installiert"}
    rpt.models = model_status

    # --- Reference-Bundles ------------------------------------------------
    refs_dir = paths.VOICE_REFS_DIR
    ref_count = 0
    ref_invalid = 0
    ref_wav_missing = 0
    if refs_dir.exists():
        for wav in refs_dir.glob("*.wav"):
            ref_count += 1
            manifest = wav.with_suffix(".wav.json")
            if not manifest.exists():
                ref_wav_missing += 1
                continue
            try:
                import json as _json
                _json.loads(manifest.read_text(encoding="utf-8"))
            except Exception:                              # noqa: BLE001
                ref_invalid += 1
    rpt.add(CheckResult(
        "Referenz-Bundles", True,
        f"{ref_count} WAVs in {refs_dir}"
        + (f" · {ref_wav_missing} ohne Manifest" if ref_wav_missing else "")
        + (f" · {ref_invalid} ungültig" if ref_invalid else "")))
    return rpt
