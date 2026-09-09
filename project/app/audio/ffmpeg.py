"""ffmpeg-Lokalisierung und -Ausführung.

Reihenfolge: tools/ffmpeg (mitgeliefert vom Installer) -> PATH ->
Windows-Standardpfade. Fehlt ffmpeg, arbeitet die Anwendung mit dem
numpy-Fallback-Mastering (Lautheit via eigener R128-Messung), kann aber
kein MP3 erzeugen (Hinweis in UI/Logs).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .. import paths
from ..logging_setup import get_logger

log = get_logger("ffmpeg")

_FF_CANDIDATES_WIN = [
    r"C:\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
]


def find_ffmpeg() -> str | None:
    local = paths.TOOLS_DIR / "ffmpeg" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if local.is_file():
        return str(local)
    local2 = paths.TOOLS_DIR / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if local2.is_file():
        return str(local2)
    found = shutil.which("ffmpeg")
    if found:
        return found
    for p in _FF_CANDIDATES_WIN:
        if Path(p).exists():
            return p
    return None


def ffmpeg_available() -> bool:
    return find_ffmpeg() is not None


def run_ffmpeg(args: list[str], timeout_s: int = 600) -> tuple[bool, str]:
    ff = find_ffmpeg()
    if not ff:
        return False, "ffmpeg nicht gefunden"
    cmd = [ff] + args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout_s)
        if proc.returncode != 0:
            return False, (proc.stderr or "")[-2000:]
        return True, (proc.stderr or "")[-500:]
    except subprocess.TimeoutExpired:
        return False, f"ffmpeg-Timeout nach {timeout_s}s"
    except OSError as e:
        return False, str(e)


def ffmpeg_version() -> str:
    ff = find_ffmpeg()
    if not ff:
        return ""
    try:
        out = subprocess.run([ff, "-version"], capture_output=True,
                             text=True, timeout=10)
        return (out.stdout or "").splitlines()[0][:120]
    except Exception:
        return ""
