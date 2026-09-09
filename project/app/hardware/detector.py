"""Hardware-Erkennung und automatische Betriebsartenwahl (Anforderung 3 + 4).

Die Erkennung ist bewusst konservativ: GPU-Betrieb wird nur gemeldet, wenn
Torch CUDA wirklich initialisieren kann. Alle Infos stehen dem Bericht und der
UI zur Verfügung.
"""
from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..logging_setup import get_logger

log = get_logger("hardware")

# Blackwell (RTX 50xx, sm_120) benötigt CUDA >= 12.8 und PyTorch >= 2.7 (cu128).
MIN_CUDA_DRIVER_blackwell = (12, 8)
BLACKWELL_SM = (12, 0)


@dataclass
class HardwareInfo:
    os: str = ""
    cpu: str = ""
    cpu_cores_physical: int = 0
    cpu_threads: int = 0
    ram_total_gb: float = 0.0
    ram_available_gb: float = 0.0
    gpu_name: str = ""
    gpu_vendor: str = ""
    gpu_vram_total_gb: float = 0.0
    gpu_vram_free_gb: float = 0.0
    driver_version: str = ""
    cuda_available: bool = False
    cuda_version: str = ""
    torch_version: str = ""
    torch_cuda_version: str = ""
    device_capability: Optional[List[int]] = None
    torch_gpu_ok: bool = False          # CUDA in Torch tatsächlich nutzbar
    torch_gpu_error: str = ""
    mode: str = "cpu"                   # gpu | gpu_conservative | cpu
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__).copy()

    @property
    def gpu_usable(self) -> bool:
        return self.mode in ("gpu", "gpu_conservative")


def _query_nvidia_smi() -> Dict[str, str]:
    """nvidia-smi abfragen (Name, VRAM, Treiber, CUDA-Version)."""
    info: Dict[str, str] = {}
    smi = shutil.which("nvidia-smi")
    if not smi:
        # Windows-typischer Fallback-Pfad
        for p in (
            r"C:\Windows\System32\nvidia-smi.exe",
            r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
        ):
            if os.path.exists(p):
                smi = p
                break
    if not smi:
        return info
    try:
        out = subprocess.run(
            [smi, "--query-gpu=name,driver_version,memory.total,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            parts = [p.strip() for p in out.stdout.strip().splitlines()[0].split(",")]
            if len(parts) >= 4:
                info["name"] = parts[0]
                info["driver"] = parts[1]
                info["vram_total_mb"] = parts[2]
                info["vram_free_mb"] = parts[3]
        # CUDA-Version via nvidia-smi
        out2 = subprocess.run([smi], capture_output=True, text=True, timeout=10)
        for line in out2.stdout.splitlines():
            if "CUDA Version" in line:
                info["cuda"] = line.split("CUDA Version:")[-1].strip().split()[0]
                break
    except (OSError, subprocess.SubprocessError) as e:
        log.debug(f"nvidia-smi nicht lesbar: {e}")
    return info


def _ram_gb() -> tuple[float, float]:
    try:
        import psutil
        mem = psutil.virtual_memory()
        return mem.total / 1e9, mem.available / 1e9
    except Exception:
        if platform.system() == "Windows":
            class STAT(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong)]
            st = STAT()
            st.dwLength = ctypes.sizeof(STAT)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))  # type: ignore[attr-defined]
            return st.ullTotalPhys / 1e9, st.ullAvailPhys / 1e9
        return 0.0, 0.0


def _cpu_counts() -> tuple[int, int, str]:
    name = platform.processor() or ""
    try:
        import psutil
        phys = psutil.cpu_count(logical=False) or os.cpu_count() or 1
        logi = psutil.cpu_count(logical=True) or phys
        if platform.system() == "Windows":
            freq = psutil.cpu_freq()
            if freq and freq.max:
                name = f"{name} @ {freq.max:.1f} GHz".strip()
        return phys, logi, name or "Unbekannt"
    except Exception:
        n = os.cpu_count() or 1
        return n, n, name or "Unbekannt"


def detect_hardware() -> HardwareInfo:
    info = HardwareInfo()
    info.os = f"{platform.system()} {platform.release()} ({platform.machine()})"

    phys, logi, cpu_name = _cpu_counts()
    info.cpu = cpu_name
    info.cpu_cores_physical = phys
    info.cpu_threads = logi

    ram_t, ram_a = _ram_gb()
    info.ram_total_gb = round(ram_t, 1)
    info.ram_available_gb = round(ram_a, 1)

    smi = _query_nvidia_smi()
    if smi.get("name"):
        info.gpu_name = smi["name"]
        info.gpu_vendor = "NVIDIA"
        info.driver_version = smi.get("driver", "")
        info.cuda_version = smi.get("cuda", "")
        try:
            info.gpu_vram_total_gb = round(float(smi.get("vram_total_mb", 0)) / 1024, 2)
            info.gpu_vram_free_gb = round(float(smi.get("vram_free_mb", 0)) / 1024, 2)
        except ValueError:
            pass

    # --- Torch-Prüfung: niemals blind CUDA annehmen (Anforderung 3) ---------
    try:
        import torch  # noqa: WPS433
        info.torch_version = torch.__version__
        info.torch_cuda_version = getattr(torch.version, "cuda", "") or ""
        if torch.cuda.is_available():
            info.cuda_available = True
            try:
                idx = torch.cuda.current_device()
                if not info.gpu_name:
                    info.gpu_name = torch.cuda.get_device_name(idx)
                    info.gpu_vendor = "NVIDIA"
                info.device_capability = list(torch.cuda.get_device_capability(idx))
                free_b, total_b = torch.cuda.mem_get_info(idx)
                info.gpu_vram_total_gb = round(total_b / 1e9, 2)
                info.gpu_vram_free_gb = round(free_b / 1e9, 2)
                # echter Mini-Test: Tensor auf GPU anlegen und zurückholen
                t = torch.ones(64, device="cuda")
                _ = float(t.sum())
                del t
                torch.cuda.synchronize()
                info.torch_gpu_ok = True
            except Exception as e:  # pragma: no cover
                info.torch_gpu_error = f"CUDA-Test fehlgeschlagen: {e}"
        else:
            info.torch_gpu_error = "torch.cuda.is_available() == False"
    except ImportError:
        info.torch_gpu_error = "PyTorch ist nicht installiert"
    except Exception as e:
        info.torch_gpu_error = f"PyTorch-Fehler: {e}"

    # --- Blackwell-Kompatibilität prüfen -----------------------------------
    if info.gpu_vendor == "NVIDIA" and info.device_capability is not None:
        sm = tuple(info.device_capability)
        if sm >= BLACKWELL_SM:
            if not info.torch_gpu_ok:
                info.warnings.append(
                    "RTX-50xx (Blackwell) erkannt, aber CUDA in PyTorch nicht nutzbar. "
                    "PyTorch >= 2.7 mit CUDA 12.8 (cu128) ist erforderlich – "
                    "bitte install.ps1 erneut ausführen."
                )

    # --- Betriebsart wählen (Anforderung 4) ---------------------------------
    if info.torch_gpu_ok and info.gpu_vram_total_gb >= 6.0:
        info.mode = "gpu"                       # 1.7B komfortabel möglich
    elif info.torch_gpu_ok and info.gpu_vram_total_gb >= 4.0:
        info.mode = "gpu_conservative"          # VRAM-schonend (0.6B / kurze Segmente)
    else:
        info.mode = "cpu"
        if info.gpu_name and not info.torch_gpu_ok:
            info.warnings.append(
                f"GPU '{info.gpu_name}' vorhanden, aber CUDA nicht nutzbar "
                f"({info.torch_gpu_error}). Es wird der CPU-Modus verwendet – "
                "deutlich langsamer, aber funktionsfähig."
            )
        elif not info.gpu_name:
            info.warnings.append("Keine NVIDIA-GPU erkannt. CPU-Modus (langsam).")

    if info.mode == "cpu" and info.ram_total_gb < 16:
        info.warnings.append(
            "Weniger als 16 GB RAM im CPU-Modus: das 1.7B-Modell passt ggf. nicht "
            "in den Arbeitsspeicher. Das 0.6B-Modell wird bevorzugt."
        )

    log.info(
        f"Hardware: {info.cpu} | {info.cpu_cores_physical}C/{info.cpu_threads}T | "
        f"RAM {info.ram_total_gb} GB | GPU {info.gpu_name or 'keine'} "
        f"({info.gpu_vram_total_gb} GB) | Torch {info.torch_version} "
        f"cu{info.torch_cuda_version} | Modus: {info.mode}"
    )
    for w in info.warnings:
        log.warning("HW-Warnung: %s", w)
    return info


def recommend_model_size(info: HardwareInfo, preference: str = "auto") -> str:
    """'1.7B' oder '0.6B' – Qualität first, aber stabil (Anforderung 48/63)."""
    if preference in ("1.7B", "0.6B"):
        return preference
    if info.mode == "gpu":
        return "1.7B"       # bessere Deutsch-Qualität (WER 0.634 vs. 0.990)
    if info.mode == "gpu_conservative":
        return "1.7B" if info.gpu_vram_free_gb >= 5.0 else "0.6B"
    # CPU: 0.6B ist die einzige praktikable Wahl
    return "0.6B"


def recommend_torch_dtype(info: HardwareInfo) -> str:
    if info.mode.startswith("gpu"):
        return "bfloat16"
    return "float32"


def vram_snapshot() -> tuple[float, float]:
    """(free_gb, total_gb) – GPU; im CPU-Modus (0,0)."""
    try:
        import torch
        if torch.cuda.is_available():
            free_b, total_b = torch.cuda.mem_get_info()
            return round(free_b / 1e9, 2), round(total_b / 1e9, 2)
    except Exception:
        pass
    return 0.0, 0.0
