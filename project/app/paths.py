"""Zentrale Pfadverwaltung für VoiceOverApp.

Alle Pfade werden relativ zum Wurzelverzeichnis der Anwendung aufgelöst
(Verzeichnis, das START.bat / app/ enthält). Funktioniert unter Windows,
Linux und macOS (für Tests).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# app/..  => Wurzelverzeichnis der Anwendung
# VOICEOVER_ROOT erlaubt isolierte Testläufe (Testsuite).
# Eingefrorene EXE (PyInstaller, §38): Ressourcen liegen neben der EXE.
APP_DIR = Path(__file__).resolve().parent
if getattr(sys, "frozen", False):            # VoiceOverApp.exe
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(os.environ.get("VOICEOVER_ROOT") or APP_DIR.parent)

INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"
CACHE_DIR = ROOT / "cache"

# Model directory resolution priority:
# 1. VOICEOVER_MODELS_DIR (explicit override)
# 2. VOICEOVER_RUNTIME_ROOT/models (runtime location with pre-downloaded models)
# 3. ROOT/models (repository local, requires download)
if os.environ.get("VOICEOVER_MODELS_DIR"):
    MODELS_DIR = Path(os.environ["VOICEOVER_MODELS_DIR"])
elif os.environ.get("VOICEOVER_RUNTIME_ROOT"):
    MODELS_DIR = Path(os.environ["VOICEOVER_RUNTIME_ROOT"]) / "models"
else:
    MODELS_DIR = ROOT / "models"

CONFIG_DIR = ROOT / "config"
PRONUNCIATION_DIR = ROOT / "pronunciation"
LOGS_DIR = ROOT / "logs"
BENCHMARK_DIR = ROOT / "benchmark"
TOOLS_DIR = ROOT / "tools"

CACHE_AUDIO_DIR = CACHE_DIR / "audio"
CACHE_META_DIR = CACHE_DIR / "metadata"
CACHE_SEGMENT_DIR = CACHE_DIR / "segments"
CACHE_PROJECT_DIR = CACHE_DIR / "projects"
VOICE_REFS_DIR = Path(os.environ.get("VOICEOVER_REFS_DIR") or str(CACHE_DIR / "voice_refs"))

# Versionierte Referenz-Bundles (werden mit dem Repo/Release ausgeliefert).
# Diese Dateien werden NICHT zur Laufzeit geschrieben; sie werden einmalig
# beim Release-Build/Import in das Repo gestellt. Die Laufzeit-Logik
# sucht eine Referenz zuerst im Runtime-Cache (VOICE_REFS_DIR), dann im
# mitgelieferten Bundle-Verzeichnis, und materialisiert sie bei Bedarf
# automatisch in den Cache. VD-E wird aus der Golden Reference gebootstrappt.
BUNDLED_REF_DIR = APP_DIR / "voices" / "bundles"
VD_E_GOLDEN_REF_PATH = ROOT / "VD-E_GOLDEN_REFERENCE" / "VD-E.wav"
VD_E_EXPECTED_SHA256 = "b156c02a60a873ad95fc92390c4a136c85308b20188373cd734bee5e5e5f2025"

CONFIG_FILE = CONFIG_DIR / "config.json"
PRESETS_FILE = CONFIG_DIR / "presets.json"
VOICES_FILE = CONFIG_DIR / "voices.json"
VERSIONS_FILE = ROOT / "versions.json"
ENVIRONMENT_FILE = ROOT / "environment.json"
INSTALL_MARKER = ROOT / ".installed"
PRONUNCIATION_FILE = PRONUNCIATION_DIR / "pronunciation.json"
PRONUNCIATION_BUILTINS_DE = APP_DIR / "pronunciation" / "builtins_de.json"
PRONUNCIATION_BUILTINS_EN = APP_DIR / "pronunciation" / "builtins_en.json"

STATE_DIR = CACHE_DIR / "state"


def ensure_directories() -> None:
    """Erstellt alle benötigten Verzeichnisse (idempotent)."""
    for d in (
        INPUT_DIR, OUTPUT_DIR, CACHE_DIR, MODELS_DIR, CONFIG_DIR,
        PRONUNCIATION_DIR, LOGS_DIR, BENCHMARK_DIR, TOOLS_DIR,
        CACHE_AUDIO_DIR, CACHE_META_DIR, CACHE_SEGMENT_DIR,
        CACHE_PROJECT_DIR, VOICE_REFS_DIR, STATE_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)
    # BUNDLED_REF_DIR ist eine *Quell*-Ressource (mit Repo ausgeliefert)
    # und wird NICHT erstellt, wenn sie fehlt (sonst würden wir einen
    # leeren Ordner im Cache erzeugen). Sie muss im Release enthalten sein.
    # VD-E-Golden-Ordner wird ebenfalls nicht erstellt (Read-Only).
    # Hugging-Face-Cache lokal bündeln (Models-Ordner), bevor hf importiert
    os.environ.setdefault("HF_HOME", str(MODELS_DIR / "hf"))


def app_root() -> Path:
    return ROOT


def python_executable() -> str:
    """Python-Interpreter des aktuellen Prozesses (für Subprozesse)."""
    return sys.executable or "python"


def in_bundle_check() -> bool:
    return (ROOT / "START.bat").exists() or (ROOT / "START.ps1").exists()


def env_flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")
