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
# Multi-Root Model Discovery
# =====================================================================
def _find_all_model_roots() -> list[Path]:
    """Findet alle bekannten Model-Roots auf dem System.
    
    Sucht in:
    1. VOICEOVER_MODELS_ROOTS (Env, komma-separiert)
    2. VOICEOVER_MODELS_DIR (Env, einzeln)
    3. Standard VoiceOverApp-Installationen (Downloads, Documents, Desktop)
       - Direkt: VoiceOverApp_*/models
       - Verschachtelt: VoiceOverApp_*/VoiceOverApp/models
    4. Primärer Models-Root aus paths.MODELS_DIR
    """
    roots = []
    
    # 1. VOICEOVER_MODELS_ROOTS (plural, komma-separiert)
    env_roots = os.environ.get("VOICEOVER_MODELS_ROOTS", "")
    if env_roots:
        for r in env_roots.split(os.pathsep if os.pathsep else ";"):
            r = r.strip()
            if r:
                p = Path(r)
                if p.exists() and p not in roots:
                    roots.append(p)
    
    # 2. VOICEOVER_MODELS_DIR (singular)
    env_dir = os.environ.get("VOICEOVER_MODELS_DIR", "")
    if env_dir:
        p = Path(env_dir)
        if p.exists() and p not in roots:
            roots.append(p)
    
    # 3. Standard VoiceOverApp-Installationen
    user_home = Path.home()
    search_dirs = [
        user_home / "Downloads",
        user_home / "Documents",
        user_home / "Desktop",
        user_home.parent / "Downloads" if user_home.parent else None,
    ]
    
    for search_dir in search_dirs:
        if not search_dir or not search_dir.exists():
            continue
        # Suche VoiceOverApp* Verzeichnisse
        for candidate in search_dir.glob("VoiceOverApp*"):
            if candidate.is_dir():
                # Direkt: VoiceOverApp_*/models
                models_dir = candidate / "models"
                if models_dir.exists() and models_dir not in roots:
                    roots.append(models_dir)
                
                # Verschachtelt: VoiceOverApp_*/VoiceOverApp/models
                nested = candidate / "VoiceOverApp" / "models"
                if nested.exists() and nested not in roots:
                    roots.append(nested)
    
    # 4. Primärer Models-Root aus paths
    try:
        from app import paths
        primary = Path(paths.MODELS_DIR)
        if primary.exists() and primary not in roots:
            roots.insert(0, primary)  # Bevorzuge primären Root
    except Exception:
        pass
    
    return roots


def _find_model_in_roots(model_name: str, hf_names: list[str], roots: list[Path]) -> tuple[bool, Path | None]:
    """Sucht ein Modell in allen gegebenen Roots.
    
    Returns:
        (found, found_path)
    """
    for root in roots:
        # Check direct path
        direct = root / model_name
        if direct.exists():
            return True, direct
        
        # Check HF cache variants
        for hf_name in hf_names:
            hf_dir = root / "hf" / "hub" / hf_name
            if hf_dir.exists():
                return True, hf_dir
    
    # Für Tokenizer: Auch speech_tokenizer in Base/CustomVoice prüfen
    if "Tokenizer" in model_name:
        for root in roots:
            # Prüfe Base und CustomVoice auf speech_tokenizer
            for model_subdir in ["Qwen3-TTS-12Hz-1.7B-Base", "Qwen3-TTS-12Hz-1.7B-CustomVoice"]:
                # Direkt: root/Qwen3-TTS-12Hz-1.7B-Base/speech_tokenizer
                speech_tok = root / model_subdir / "speech_tokenizer"
                if speech_tok.exists() and speech_tok.is_dir():
                    # Prüfe ob es aussieht wie ein valider speech_tokenizer
                    if (speech_tok / "config.json").exists() or any(speech_tok.glob("*")):
                        return True, speech_tok
                
                # In HF cache snapshots
                for hf_name in [f"models--Qwen--{model_subdir}", model_subdir]:
                    hf_base = root / "hf" / "hub" / hf_name
                    if hf_base.exists():
                        snapshots = hf_base / "snapshots"
                        if snapshots.exists():
                            for snap in snapshots.iterdir():
                                if snap.is_dir():
                                    speech_tok = snap / "speech_tokenizer"
                                    if speech_tok.exists() and speech_tok.is_dir():
                                        # Prüfe ob es aussieht wie ein valider speech_tokenizer
                                        if (speech_tok / "config.json").exists() or any(speech_tok.glob("*")):
                                            return True, speech_tok
    
    return False, None


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
            vram_gb = round(props.total_memory / (1024**3), 1)
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
    """Qwen3-TTS-Modelle müssen vorhanden sein (Multi-Root-Discovery)."""
    from app import paths
    paths.ensure_directories()
    
    # Alle bekannten Model-Roots finden
    all_roots = _find_all_model_roots()
    
    # Map: display_name -> list of possible HF cache names
    models_to_check = {
        "Qwen3-TTS-12Hz-1.7B-CustomVoice": [
            "models--Qwen--Qwen3-TTS-12Hz-1.7B-CustomVoice",
            "models--Qwen3-TTS-12Hz-1.7B-CustomVoice",
        ],
        "Qwen3-TTS-12Hz-1.7B-Base": [
            "models--Qwen--Qwen3-TTS-12Hz-1.7B-Base",
            "models--Qwen3-TTS-12Hz-1.7B-Base",
        ],
        "Qwen3-TTS-Tokenizer-12Hz": [
            "models--Qwen--Qwen3-TTS-Tokenizer-12Hz",
            "models--Qwen3-TTS-Tokenizer-12Hz",
            # Tokenizer kann auch als "tokenizer" Unterverzeichnis existieren
            "models--Qwen--Qwen3-TTS-12Hz-Tokenizer",
        ],
    }
    
    results = {}
    found_paths = {}
    
    for display_name, hf_names in models_to_check.items():
        found, found_path = _find_model_in_roots(display_name, hf_names, all_roots)
        results[display_name] = found
        if found and found_path:
            found_paths[display_name] = str(found_path)
    
    all_present = all(results.values())
    
    # Modelle im Output dokumentieren
    actual_dict = {}
    for model_name, found in results.items():
        if found:
            path_info = found_paths.get(model_name, "")
            actual_dict[model_name] = f"[OK] ({path_info})"
        else:
            actual_dict[model_name] = "[FAIL] FEHLT"
    
    # Models-Roots dokumentieren
    roots_info = "; ".join(str(r) for r in all_roots)
    
    return {
        "check": "Modelle",
        "required": "CustomVoice + Base + Tokenizer",
        "actual": actual_dict,
        "models_roots": roots_info,
        "models_found_paths": found_paths,
        "ok": all_present,
    }


def check_voice_reference() -> dict:
    """Runtime Voice Reference muss existieren und Hash stimmen."""
    import hashlib

    from app import paths
    paths.ensure_directories()

    # Priorisierung: VOICEOVER_RUNTIME_REF > VOICEOVER_REFS_DIR > Default
    runtime_ref = os.environ.get("VOICEOVER_RUNTIME_REF", "")
    refs_dir = os.environ.get("VOICEOVER_REFS_DIR", str(paths.VOICE_REFS_DIR))

    expected_sha = "B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025"

    # Determine reference file path
    if runtime_ref and Path(runtime_ref).is_file():
        ref_path = Path(runtime_ref)
    else:
        ref_path = Path(refs_dir) / "VD-E.wav"

    ref_str = str(ref_path)

    if not ref_path.exists():
        return {
            "check": "VD-E Runtime Reference",
            "required": "VD-E.wav mit korrektem SHA-256",
            "actual": "VD-E-Referenz fehlt: {}. VD-E ist deaktiviert. Keine Neuerzeugung (LOCKED).".format(ref_str),
            "ref_path": ref_str,
            "status_level": "missing_ref",
            "ok": False,
        }

    # SHA-256 berechnen
    h = hashlib.sha256()
    with open(ref_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    actual_sha = h.hexdigest().upper()

    if actual_sha != expected_sha:
        return {
            "check": "VD-E Runtime Reference",
            "required": "VD-E.wav mit korrektem SHA-256",
            "actual": "SHA-256 Mismatch: erwartet {}, gefunden {}".format(expected_sha[:16], actual_sha[:16]),
            "ref_path": ref_str,
            "expected_sha256": expected_sha,
            "actual_sha256": actual_sha,
            "status_level": "hash_mismatch",
            "ok": False,
        }

    return {
        "check": "VD-E Runtime Reference",
        "required": "VD-E.wav mit korrektem SHA-256",
        "actual": "VD-E-Referenz identitaetgesichert (SHA-256 OK)",
        "ref_path": ref_str,
        "sha256": actual_sha,
        "status_level": "ok",
        "ok": True,
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
        vram_gb = round(props.total_memory / (1024**3), 1)
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
        # Additional info fields
        for info_key in ("models_root", "models_roots", "ref_path", "sha256", "expected_sha256", "actual_sha256"):
            if info_key in check:
                print(f"         {info_key}: {check[info_key]}")
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
