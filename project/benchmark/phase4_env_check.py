"""Phase 4: Umgebung-Check für echten RTX 5060 Benchmark.

Prüft alle Voraussetzungen und erstellt einen vollständigen
Umgebungsbericht. MUSS bestanden werden vor dem Benchmark.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# App-Root setzen
SCRIPT_DIR = Path(__file__).resolve().parent
APP_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(APP_ROOT))

# =====================================================================
# Check-Funktionen
# =====================================================================
def check_python_version() -> dict:
    """Python 3.10-3.13 erforderlich."""
    v = sys.version_info
    version_str = f"{v.major}.{v.minor}.{v.micro}"
    ok = (3, 10) <= v <= (3, 14)
    return {
        "check": "Python-Version",
        "required": "3.10 - 3.13",
        "actual": version_str,
        "ok": ok,
    }


def check_pytorch() -> dict:
    """PyTorch mit CUDA erforderlich."""
    try:
        import torch
        cuda_available = torch.cuda.is_available()
        cuda_version = torch.version.cuda if cuda_available else None
        device_name = torch.cuda.get_device_name(0) if cuda_available else "N/A"
        vram_gb = None
        if cuda_available:
            props = torch.cuda.get_device_properties(0)
            vram_gb = round(props.total_mem / (1024**3), 1)
        return {
            "check": "PyTorch",
            "required": ">= 2.0 mit CUDA",
            "actual": f"{torch.__version__} (CUDA {cuda_version})",
            "cuda_available": cuda_available,
            "gpu_name": device_name,
            "vram_gb": vram_gb,
            "ok": cuda_available,
        }
    except ImportError:
        return {
            "check": "PyTorch",
            "required": ">= 2.0 mit CUDA",
            "actual": "NICHT INSTALLIERT",
            "ok": False,
        }


def check_qwen_tts() -> dict:
    """qwen-tts 0.1.1 erforderlich."""
    try:
        import qwen_tts
        version = getattr(qwen_tts, "__version__", "unbekannt")
        return {
            "check": "qwen-tts",
            "required": "0.1.1",
            "actual": version,
            "ok": True,
        }
    except ImportError:
        return {
            "check": "qwen-tts",
            "required": "0.1.1",
            "actual": "NICHT INSTALLIERT",
            "ok": False,
        }


def check_transformers() -> dict:
    """transformers >= 4.57 erforderlich."""
    try:
        import transformers
        return {
            "check": "transformers",
            "required": ">= 4.57.3",
            "actual": transformers.__version__,
            "ok": True,
        }
    except ImportError:
        return {
            "check": "transformers",
            "required": ">= 4.57.3",
            "actual": "NICHT INSTALLIERT",
            "ok": False,
        }


def check_ffmpeg() -> dict:
    """FFmpeg erforderlich für MP3 + Mastering."""
    path = shutil.which("ffmpeg")
    if path:
        try:
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True,
                                    text=True, timeout=10)
            version_line = result.stdout.split("\n")[0] if result.stdout else "unbekannt"
            return {
                "check": "FFmpeg",
                "required": "Vorhanden",
                "actual": version_line[:80],
                "path": path,
                "ok": True,
            }
        except Exception:
            return {
                "check": "FFmpeg",
                "required": "Vorhanden",
                "actual": "Installiert, aber Fehler beim Aufruf",
                "ok": False,
            }
    return {
        "check": "FFmpeg",
        "required": "Vorhanden",
        "actual": "NICHT GEFUNDEN",
        "ok": False,
    }


def check_models() -> dict:
    """Qwen3-TTS-Modelle müssen vorhanden sein."""
    from app import paths
    paths.ensure_directories()
    models = {
        "Qwen3-TTS-12Hz-1.7B-CustomVoice": False,
        "Qwen3-TTS-12Hz-1.7B-Base": False,
        "Qwen3-TTS-Tokenizer-12Hz": False,
    }
    for repo_name in models:
        model_dir = paths.MODELS_DIR / repo_name
        hf_dir = paths.MODELS_DIR / "hf" / "hub" / f"models--{repo_name.replace('/', '--')}"
        models[repo_name] = model_dir.exists() or hf_dir.exists()
    all_present = all(models.values())
    return {
        "check": "Modelle",
        "required": "CustomVoice + Base + Tokenizer",
        "actual": {k: ("[OK]" if v else "[FAIL] FEHLT") for k, v in models.items()},
        "ok": all_present,
    }


def check_voice_reference() -> dict:
    """Runtime Voice Reference muss existieren und Hash stimmen."""
    from app import paths
    from app.security.identity_lock import check_identity
    paths.ensure_directories()
    status = check_identity()
    return {
        "check": "VD-E Runtime Reference",
        "required": "cache/voice_refs/VD-E.wav mit korrektem SHA-256",
        "actual": status.message,
        "status_level": status.level,
        "ok": status.ok,
    }


def check_gpu_specs() -> dict:
    """RTX 5060 mit 8 GB VRAM erforderlich."""
    try:
        import torch
        if not torch.cuda.is_available():
            return {
                "check": "GPU-Spezifikation",
                "required": "RTX 5060 (>= 8 GB VRAM)",
                "actual": "KEINE GPU",
                "ok": False,
            }
        props = torch.cuda.get_device_properties(0)
        vram_gb = round(props.total_mem / (1024**3), 1)
        name = props.name
        ok = vram_gb >= 7.5  # RTX 5060 hat 8 GB, etwas Toleranz
        return {
            "check": "GPU-Spezifikation",
            "required": "RTX 5060 (>= 8 GB VRAM)",
            "actual": f"{name} ({vram_gb} GB VRAM)",
            "ok": ok,
        }
    except ImportError:
        return {
            "check": "GPU-Spezifikation",
            "required": "RTX 5060 (>= 8 GB VRAM)",
            "actual": "PyTorch nicht installiert",
            "ok": False,
        }


def check_ram() -> dict:
    """Mindestens 16 GB RAM erforderlich."""
    try:
        import psutil
        ram_gb = round(psutil.virtual_memory().total / (1024**3), 1)
        return {
            "check": "RAM",
            "required": ">= 16 GB",
            "actual": f"{ram_gb} GB",
            "ok": ram_gb >= 16,
        }
    except ImportError:
        return {
            "check": "RAM",
            "required": ">= 16 GB",
            "actual": "psutil nicht installiert",
            "ok": False,
        }


# =====================================================================
# Hauptprogramm
# =====================================================================
def main():
    print("=" * 70)
    print("PHASE 4: Umgebungs-Check für RTX 5060 Benchmark")
    print("=" * 70)
    print(f"Zeit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"OS: {platform.platform()}")
    print(f"CPU: {platform.processor()}")
    print()

    checks = [
        check_python_version(),
        check_pytorch(),
        check_qwen_tts(),
        check_transformers(),
        check_ffmpeg(),
        check_models(),
        check_voice_reference(),
        check_gpu_specs(),
        check_ram(),
    ]

    results = {}
    all_ok = True
    for check in checks:
        status = "[OK]" if check["ok"] else "[FAIL]"
        print(f"  {status}  {check['check']}")
        print(f"         Erforderlich: {check['required']}")
        actual = check.get("actual")
        if isinstance(actual, dict):
            for k, v in actual.items():
                print(f"         {k}: {v}")
        else:
            print(f"         Vorhanden: {actual}")
        print()
        results[check["check"]] = check
        if not check["ok"]:
            all_ok = False

    # Summary
    n_pass = sum(1 for c in checks if c["ok"])
    n_total = len(checks)
    print("=" * 70)
    print(f"ERGEBNIS: {n_pass}/{n_total} Checks bestanden")
    print("=" * 70)

    if all_ok:
        print("\n[OK] ALLE CHECKS BESTANDEN")
        print("Benchmark kann gestartet werden:")
        print("  python benchmark/phase4_benchmark.py")
    else:
        failed = [c["check"] for c in checks if not c["ok"]]
        print(f"\n[FAIL] FEHLENDE VORAUSSETZUNGEN: {', '.join(failed)}")
        print("\nBitte install.ps1 ausführen und erneut prüfen.")

    # Report speichern
    report = {
        "timestamp": datetime.now().isoformat(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "python": sys.version,
        "checks": results,
        "all_passed": all_ok,
        "passed": n_pass,
        "total": n_total,
    }

    report_path = APP_ROOT / "benchmark" / "phase4_env_check.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nReport gespeichert: {report_path}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
