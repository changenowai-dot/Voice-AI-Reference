"""Prüft, dass alle notwendigen Source-Module aus einem sauberen Git-
Checkout importiert werden können, ohne auf lokalen Cache oder nicht-
versionierte Dateien angewiesen zu sein.

Das ist der kritische Test gegen den app/cache-Manager-Fehler: nach
einem frischen ``git clone`` muss ``from app.cache.manager import
CacheManager`` OHNE lokale Reparatur funktionieren.

Wir führen diesen Test ZUSÄTZLICH in einem temporären frischen Checkout
aus (``--fresh-checkout``); der Standardlauf prüft nur den aktuellen
Arbeitsbaum.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


CHECK_SCRIPT = """
import sys, json
mods = ['app.cache.manager', 'app.project.pipeline', 'app.jobs.runner',
        'app.preflight', 'app.tts.model_pool',
        'app.tts.qwen_engine', 'app.audio.assemble',
        'app.voices.registry', 'app.prosody.german', 'app.prosody.english']
results = []
for m in mods:
    try:
        __import__(m)
        results.append((m, 'OK'))
    except Exception as e:
        results.append((m, '%s: %s' % (type(e).__name__, e)))
print(json.dumps(results))
"""


def _check_imports(python_exe: str, project_root: Path) -> list[tuple[str, str]]:
    """Import-Check isoliert in einem Subprocess mit project/ als sys.path.
    GUI (tkinter) wird hier absichtlich NICHT geprüft, weil tkinter in
    Headless-Umgebungen fehlen kann – die GUI-Module sind über
    py_compile abgedeckt.
    """
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("VOICEOVER_REFS_DIR", None)
    env.pop("VOICEOVER_RUNTIME_ROOT", None)
    env["PYTHONPATH"] = str(project_root / "project")
    res = subprocess.run([python_exe, "-c", CHECK_SCRIPT], capture_output=True,
                         text=True, env=env, timeout=60)
    if res.returncode != 0:
        raise RuntimeError(
            "Import-Check-Prozess fehlgeschlagen (rc=%d):\nstdout: %s\nstderr: %s"
            % (res.returncode, res.stdout[-1000:], res.stderr[-2000:]))
    return json.loads(res.stdout.strip().splitlines()[-1])


def _fresh_checkout_test(python_exe: str, commit_sha: str) -> dict:
    """Klon in ein temp-Verzeichnis, Checkout auf genau den Commit, dann
    Import-Check ausführen – ohne lokalen Cache."""
    tmp = Path(tempfile.mkdtemp(prefix="voiceover_fresh_"))
    try:
        subprocess.run(["git", "clone", "--depth=1", "-b",
                        "arena/01a08d48-voice-ai-reference",
                        str(ROOT), str(tmp / "clone")],
                       check=True, capture_output=True, timeout=120)
        clone = tmp / "clone"
        subprocess.run(["git", "-C", str(clone), "checkout", commit_sha],
                       check=True, capture_output=True, timeout=30)
        results = _check_imports(python_exe, clone)
        return {"dir": str(clone), "results": results}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh-checkout", action="store_true",
                    help="Zusätzlich einen frischen Git-Klon in ein "
                         "Temp-Verzeichnis machen und dort testen.")
    ap.add_argument("--commit", default="HEAD",
                    help="Commit-SHA für Fresh-Checkout-Test.")
    args = ap.parse_args()

    py = sys.executable
    fails = 0

    print("=== 1. Import-Check im aktuellen Arbeitsbaum ===")
    cur = _check_imports(py, ROOT)
    for mod, status in cur:
        ok = (status == "OK")
        print(f"  [{'OK' if ok else 'FAIL'}] {mod}: {status}")
        if not ok:
            fails += 1

    if args.fresh_checkout:
        print()
        print("=== 2. Import-Check in frischem Git-Checkout ===")
        sha = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", args.commit], text=True).strip()
        print(f"   Commit: {sha}")
        try:
            fc = _fresh_checkout_test(py, sha)
            for mod, status in fc["results"]:
                ok = (status == "OK")
                print(f"  [{'OK' if ok else 'FAIL'}] {mod}: {status}")
                if not ok:
                    fails += 1
        except Exception as e:
            print(f"  [FAIL] Fresh-Checkout konnte nicht erstellt werden: {e}")
            fails += 1

    # .gitignore prüfen: project/app/cache darf NICHT mehr ignoriert werden
    print()
    print("=== 3. .gitignore Prüfung ===")
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    if "/cache/" not in gi and "cache/" in gi:
        print("  [FAIL] .gitignore enthält 'cache/' ohne '/' – das ignoriert "
              "project/app/cache/ und alle Unterordner!")
        fails += 1
    else:
        # Sicherstellen, dass die Root-Cache-Daten ignoriert werden
        if "/cache/" in gi:
            print("  [OK] /cache/ ist Root-nur (Runtime-Daten)")
        else:
            print("  [WARN] .gitignore matcht 'cache/' möglicherweise zu breit")
    # project/app/cache/manager.py muss im Git tracked sein
    r = subprocess.run(["git", "-C", str(ROOT), "ls-files",
                        "project/app/cache/manager.py"],
                       capture_output=True, text=True)
    if "manager.py" not in r.stdout:
        print("  [FAIL] project/app/cache/manager.py ist NICHT getrackt!")
        fails += 1
    else:
        print("  [OK] project/app/cache/manager.py ist im Git getrackt")
    # project/app/cache/__init__.py muss auch getrackt sein
    r = subprocess.run(["git", "-C", str(ROOT), "ls-files",
                        "project/app/cache/__init__.py"],
                       capture_output=True, text=True)
    if "__init__.py" not in r.stdout:
        print("  [FAIL] project/app/cache/__init__.py ist NICHT getrackt!")
        fails += 1
    else:
        print("  [OK] project/app/cache/__init__.py ist im Git getrackt")

    print()
    if fails:
        print(f"{fails} SOURCE-COMPLETENESS PROBLEM(E) GEFUNDEN")
        return 1
    print("ALL SOURCE-COMPLETENESS TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
