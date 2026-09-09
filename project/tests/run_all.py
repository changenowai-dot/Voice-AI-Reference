"""Testsuite-Launcher (ohne externe Test-Frameworks).

Führt alle test_*.py-Module aus. Jede Funktion test_* wird ausgeführt.
Läuft isoliert über VOICEOVER_ROOT (keine Vermischung mit echten Ordnern).

Abdeckung der Anforderungs-Tests A–Q (siehe TESTREPORT.md):
A 10s-Text · B 1min-Text · C 10min-Text · D Long-Form · E Deutsch ·
F Englisch · G Aussprache · H Wörterbuch · I mehrere Dateien ·
J Cache · K Resume · L QC · M Regeneration · N WAV · O MP3 ·
P Normalisierung · Q GPU (GPU-Teil nur auf Zielhardware, hier CPU-Pfad)
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP_ROOT = HERE.parent

# ffmpeg für Tests (Sandbox: statischer Build, persistente Ablage)
import os as _os
from pathlib import Path as _P
for _ff in (_P("/home/user/ffmpeg_tool/ffmpeg"), _P("/tmp/ffdir/ffmpeg")):
    if _ff.exists():
        try:                       # Snapshot kann das x-Bit verlieren
            _ff.chmod(0o755)
        except OSError:
            pass
        _os.environ["PATH"] = str(_ff.parent) + ":" + _os.environ.get("PATH", "")
        break

# Isolierte Testumgebung – auf der PLATTE (nicht tmpfs): Long-Form-Tests
# erzeugen hunderte MB an Audio; /tmp (tmpfs ~1 GB) läuft sonst voll.
_TMP_BASE = Path("/home/user/.voa_test_tmp")
_TMP_BASE.mkdir(parents=True, exist_ok=True)
TEST_ROOT = Path(tempfile.mkdtemp(prefix="voa_test_", dir=str(_TMP_BASE)))
os.environ["VOICEOVER_ROOT"] = str(TEST_ROOT)
sys.path.insert(0, str(APP_ROOT))


def run_all(selected: list[str] | None = None) -> int:
    os.environ.setdefault("VOICEOVER_ROOT", str(TEST_ROOT))
    # ensure fresh import state for app modules in subprocesses
    from app import paths
    paths.ensure_directories()

    modules = sorted(HERE.glob("test_*.py"))
    if selected:
        modules = [m for m in modules if any(s in m.name for s in selected)]

    total = passed = failed = 0
    failures: list[tuple[str, str]] = []
    t0 = time.perf_counter()

    for mod_path in modules:
        print(f"\n=== {mod_path.name} ===")
        spec = importlib.util.spec_from_file_location(mod_path.stem, mod_path)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception:
            traceback.print_exc()
            failures.append((mod_path.name, "MODUL-IMPORT FEHLGESCHLAGEN"))
            failed += 1
            continue
        for name in dir(mod):
            if name.startswith("test_") and callable(getattr(mod, name)):
                total += 1
                t1 = time.perf_counter()
                try:
                    getattr(mod, name)()
                    dt = time.perf_counter() - t1
                    print(f"  PASS  {name}  ({dt:.1f}s)")
                    passed += 1
                except Exception as e:
                    failed += 1
                    print(f"  FAIL  {name}: {e}")
                    traceback.print_exc(limit=3)
                    failures.append((f"{mod_path.name}::{name}", str(e)))

    print("\n" + "=" * 60)
    print(f"ERGEBNIS: {passed}/{total} bestanden, {failed} fehlgeschlagen "
          f"({time.perf_counter() - t0:.1f}s)")
    print(f"Test-Root: {TEST_ROOT}")
    for name, err in failures:
        print(f"  FEHLER: {name}: {err[:200]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sel = sys.argv[1:] or None
    code = run_all(sel)
    shutil.rmtree(TEST_ROOT, ignore_errors=True)
    sys.exit(code)
