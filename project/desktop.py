"""VoiceOverApp – Einstieg der Desktop-Anwendung (§38 Packaging).

Quellmodus:  python desktop.py   (oder VoiceOverApp.bat)
Exe-Modus:   VoiceOverApp.exe    (PyInstaller; GUI ohne Argumente,
             CLI-Flags wie --job/--headless werden an app.main geleitet)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for p in (str(ROOT), str(ROOT / "app")):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("HF_HOME", str(ROOT / "models" / "hf"))


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--gui")]
    if args:                       # CLI-Modus (§37): --job, --headless, …
        from app.main import main as cli_main
        return cli_main()
    # Normalstart (auch GUI-EXE per Doppelklick): Desktop-GUI (§3/§4).
    # Kein Webserver, kein Browser, kein Port 8750.
    from app.gui.app import run
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
