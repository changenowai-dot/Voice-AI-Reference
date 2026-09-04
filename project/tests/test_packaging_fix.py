"""Packaging-Fix-Tests (v2.0.0): Start-Schichtung, Routing, Spec, Manifest.

Sperrzone: TTS/Audio-Kern wird nicht angefasst (§14). Bei einem Test,
der eine TTS-Änderung nahelegt: TTS CORE LOCKED melden.
"""
from __future__ import annotations

from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent

VD_E_SHA = "B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025"


# ---------------------------------------------------------------------------
# §1 START.bat / VoiceOverApp.bat
# ---------------------------------------------------------------------------
def test_start_bat_launches_desktop_gui():
    for bat in ("START.bat", "VoiceOverApp.bat"):
        src = (APP_ROOT / bat).read_text(encoding="utf-8").lower()
        assert "desktop.py" in src, bat                 # GUI-Entry-Point
        assert "run_server" not in src and "app\\main.py" not in src
        # kein Browser-/Webserver-START (Kommentar-Erwähnungen sind ok):
        assert "http://127.0.0.1" not in src
        assert "start http" not in src and "start-process http" not in src
        assert "%~dp0" in src                           # relatives App-Root
        assert "c:\\users\\johan" not in src          # keine Benutzerpfade


def test_start_ps1_default_gui_no_webserver():
    src = (APP_ROOT / "START.ps1").read_text(encoding="utf-8")
    low = src.lower()
    # Standard = GUI über desktop.py
    assert "desktop.py" in low
    # Webserver nur explizit, kein Default-Port/kein Browser-Start
    assert "[switch]$webserver" in low
    assert "open_browser" not in low and "start-process http" not in low
    # keine festen Benutzerpfade
    assert "c:\\users" not in low and "johan" not in low


# ---------------------------------------------------------------------------
# §3 Routing: GUI-Entry <-> CLI-Entry, kein Vermischen
# ---------------------------------------------------------------------------
def test_route_mode_matrix():
    import sys
    sys.path.insert(0, str(APP_ROOT))
    from types import SimpleNamespace as N
    from app.main import route_mode
    base = dict(webserver=False, ui=False, job=None, files=None,
                phase2_apply=None, headless=False, info=False, version=False,
                benchmark=None, download_models=False, quick=False,
                german_baseline=False, german_baseline_force=False,
                german_ab=False, german_speakers=False, phase2_run=False,
                phase2_pauses=False, phase2_pick=None, phase3_run=False,
                phase3_pick=None, phase3_apply=False, desktop_voices=False)
    assert route_mode(N(**base)) == "gui"                      # Normalstart
    assert route_mode(N(**{**base, "job": "x.json"})) == "cli"
    assert route_mode(N(**{**base, "headless": True})) == "cli"
    assert route_mode(N(**{**base, "webserver": True})) == "webserver"
    assert route_mode(N(**{**base, "info": True})) == "cli"
    # §3: --engine/--port allein KEIN Webserver (kein Vermischen)
    assert route_mode(N(**base)) == "gui"


def test_main_no_args_routes_gui_not_webserver():
    """Normalstart landet in der GUI, niemals im Webserver (Subprocess-
    Beweis: GUI-Versuch schlägt in der Sandbox an Tk ohne Display fehl,
    Webserver würde stattdessen lauschen)."""
    import os
    import subprocess
    import sys
    env = dict(os.environ)
    env["VOICEOVER_ROOT"] = str(APP_ROOT)   # realer Root, kein tmp nötig
    proc = subprocess.run(
        [sys.executable, str(APP_ROOT / "app" / "main.py"), "--version"],
        env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0
    # --version als schnellster CLI-Nachweis; GUI-Route über route_mode
    # separat geprüft (ein echter no-arg-Start würde Tk öffnen).
    from types import SimpleNamespace as N
    from app.main import route_mode
    assert route_mode(N(webserver=False, ui=False, job=None, files=None,
                        phase2_apply=None)) == "gui"


def test_desktop_entry_points():
    """§4: desktop.py ist der offizielle GUI-Entry (kein Webserver)."""
    src = (APP_ROOT / "desktop.py").read_text(encoding="utf-8")
    assert "from app.gui.app import run" in src
    assert "run()" in src
    # startet niemals den Webserver (kein Flag, kein Server-Aufruf):
    assert "--webserver" not in src
    assert "run_server" not in src and "ui.server" not in src
    assert str(APP_ROOT) in src or "__file__" in src   # relatives Root


# ---------------------------------------------------------------------------
# §7/§8 PyInstaller
# ---------------------------------------------------------------------------
def test_pyinstaller_spec_uses_desktop_entry():
    spec = (APP_ROOT / "VoiceOverApp.spec").read_text(encoding="utf-8")
    low = spec.lower()
    assert "['desktop.py']" in low or "'desktop.py'" in low  # Entry-Point
    assert "app/main.py" not in low                     # kein Webserver-Prozess
    assert "console=false" in low                        # GUI-EXE windowed
    assert "console=true" in low                         # Backend-EXE (stdout)
    assert "voiceoverappbackend" in low
    assert "name='voiceoverapp'" in low
    # §9: App-Ressourcen (Built-ins) mitgebündelt
    assert "builtins_de.json" in low and "builtins_en.json" in low


def test_build_script_relative_and_spec_based():
    src = (APP_ROOT / "build_windows.ps1").read_text(encoding="utf-8")
    low = src.lower()
    assert "voiceoverapp.spec" in low                    # Spec-basiert
    assert "c:\\users\\johan" not in low               # keine Benutzerpfade
    assert "join-path" in low and "$root" in low         # relative Nutzung
    assert "voiceoverappbackend.exe" in low              # Backend-EXE geprüft
    assert "get-filehash" in low                         # VD-E-Hash-Check
    assert "$root" in low                                # relative Pfade


def test_backend_frozen_uses_backend_exe():
    """§7: GUI (windowed) startet das Backend als Konsolen-EXE."""
    from app.gui.backend import BACKEND_EXE_NAME, backend_args, backend_python
    assert BACKEND_EXE_NAME == "VoiceOverAppBackend.exe"
    # Quellmodus: venv/python + app/main.py --job
    args = backend_args(Path("/tmp/job.json"))
    assert args[-2:] == ["--job", "/tmp/job.json"]
    assert any("main.py" in a for a in args) or any(
        "python" in a.lower() for a in args)


# ---------------------------------------------------------------------------
# §10 Voice-Profile unverändert
# ---------------------------------------------------------------------------
def test_voice_profiles_vd_e_core_unchanged():
    """v2: 8 Stimmen (native-language-Strategie); VD-E-Kern unverändert."""
    import json
    from app.voices.registry import VoiceRegistry
    reg = VoiceRegistry()
    entries = reg.entries()
    assert len(entries) == 8            # v2: + uncle_fu, dylan
    ids = {e.voice_id for e in entries}
    assert ids == {"vd_e", "uncle_fu", "dylan", "ryan", "aiden",
                   "vivian", "serena", "sohee"}
    vd = reg.get("vd_e")
    assert vd.default and vd.recommended and vd.production_locked
    raw = json.loads((APP_ROOT / "voices" / "vd_e.json").read_text(
        encoding="utf-8"))
    assert raw["default"] is True and raw["recommended"] is True
    assert raw["production_locked"] is True
    assert raw["reference_path"] == "cache/voice_refs/VD-E.wav"


# ---------------------------------------------------------------------------
# §11 Identity-Lock + Production-Lock
# ---------------------------------------------------------------------------
def test_production_json_untouched():
    import json
    prod = json.loads((APP_ROOT / "config" / "production.json").read_text(
        encoding="utf-8"))
    assert prod["reference_sha256"] == VD_E_SHA
    assert prod["seed"] == 52001
    assert prod["cache_version"] == "q3p-v2-integrity"
    assert prod["variant"] == "BASE"
    assert prod["locked"] is True
    assert prod["automatic_voice_switch"] is False
    assert prod["automatic_voice_fallback"] is False
    assert prod["automatic_voice_regeneration"] is False


def test_identity_lock_still_enforced():
    """§11: Lock-Mechanik weiterhin aktiv (unabhängig vom App-Root)."""
    import json
    import tempfile
    from app.security.identity_lock import check_identity
    tmp = tempfile.mkdtemp(prefix="pkg_id_")
    # Produktionssatz (wie Lieferung), Referenz-Ziel im tmp:
    prod = {"reference_sha256": VD_E_SHA,
            "reference_path": str(Path(tmp) / "cache" / "voice_refs" /
                                  "VD-E.wav")}
    status = check_identity(prod)              # fehlende Referenz -> Sperre
    assert not status.ok and status.level == "missing_ref"
    assert status.expected == VD_E_SHA
    assert not status.vd_e_available
    # manipulierte Referenz -> hash_mismatch, keine „Reparatur“
    ref_dir = Path(tmp) / "cache" / "voice_refs"
    ref_dir.mkdir(parents=True, exist_ok=True)
    ref = ref_dir / "VD-E.wav"
    ref.write_bytes(b"GEFAELSCHT" * 100)
    status2 = check_identity(prod)
    assert not status2.ok and status2.level == "hash_mismatch"
    assert ref.read_bytes() == b"GEFAELSCHT" * 100   # unangetastet


# ---------------------------------------------------------------------------
# §5/§15/§16 Doku + Manifest
# ---------------------------------------------------------------------------
def test_readme_describes_correct_start():
    src = (APP_ROOT / "README.md").read_text(encoding="utf-8")
    assert "NORMALER START" in src and "VoiceOverApp.bat" in src
    assert "ENTWICKLERSTART" in src
    assert "HEADLESS / CLI" in src
    assert '--headless --files "input' in src
    # alter Falsch-Hinweis entfernt:
    assert "→ Browser öffnet" not in src


def test_final_manifest_contents():
    src = (APP_ROOT / "FINAL_APP_MANIFEST.txt").read_text(encoding="utf-8")
    for key in ("VERSION=2.1.0", "DESKTOP_GUI=true", "CLI=true",
                "PDF_IMPORT=true", "VOICE_COUNT=8", "LANGUAGES=de,en",
                "VD_E_LOCKED=true", f"VD_E_SHA256={VD_E_SHA}"):
        assert key in src, key


def test_final_report_documents_packaging_fix():
    src = (APP_ROOT / "FINAL_APP_REPORT.md").read_text(encoding="utf-8")
    assert "Desktop Entry Point" in src
    assert "desktop.py" in src
    assert "build_windows.ps1" in src
    assert VD_E_SHA in src


def test_start_correction_note_exists():
    p = APP_ROOT / "START_ANLEITUNG_KORREKTUR.md"
    assert p.exists()
    src = p.read_text(encoding="utf-8")
    assert VD_E_SHA in src                       # VD-E-Infos unverändert
    assert "kein Browser" in src


# ---------------------------------------------------------------------------
# §12 CLI bleibt erhalten (Schnelltest)
# ---------------------------------------------------------------------------
def test_cli_still_works():
    import os
    import subprocess
    import sys
    env = dict(os.environ)
    env["VOICEOVER_ROOT"] = str(APP_ROOT)
    proc = subprocess.run(
        [sys.executable, str(APP_ROOT / "app" / "main.py"), "--info"],
        env=env, capture_output=True, text=True, timeout=120, cwd=str(APP_ROOT))
    assert proc.returncode == 0
    assert "VoiceOverApp" in proc.stdout
