#!/usr/bin/env python3
"""Prueft, ob die BENOETIGTEN Qwen-Modelle vollstaendig vorhanden sind.

Verwendet DIESELBE Modell-Auflösung wie die Runtime (QwenModelPool.
_resolve_model_path) und dieselben Vollstaendigkeits-Kriterien wie der
GUI-Preflight (app/preflight.py):

  - model.safetensors vorhanden (bzw. mind. eine *.safetensors) UND
    nicht offensichtlich trunciert (< --min-safetensors-mb, Default 100 MB)
  - config.json vorhanden
  - tokenizer.json oder tokenizer_config.json vorhanden

Pflicht-Modelle (App startet produktiv sonst NICHT):
  - base        Qwen/Qwen3-TTS-12Hz-1.7B-Base         (VoiceCloneEngine)
  - customvoice Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice (QwenTTSEngine)

Optional (nur Warnung, kein Fail):
  - voicedesign Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign
  - Tokenizer   Qwen/Qwen3-TTS-Tokenizer-12Hz        (Info)

Exit-Codes: 0 = alle Pflicht-Modelle OK, 1 = mindestens eines fehlt
oder ist unvollstaendig. Laeuft OHNE torch (nur Pfad-/Datei-Pruefung).

Aufruf (in project/):
  .venv\\Scripts\\python.exe tools\\check_models.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

REQUIRED = ["base", "customvoice"]
OPTIONAL = ["voicedesign"]


def _safetensors_size_mb(p: Path) -> float:
    main = p / "model.safetensors"
    if main.is_file():
        return main.stat().st_size / (1024.0 * 1024.0)
    total = 0
    for f in p.glob("*.safetensors"):
        total += f.stat().st_size
    return total / (1024.0 * 1024.0)


def check_one(pool, name: str, min_mb: float) -> tuple[bool, str]:
    repo = pool.MODEL_REPOS[name]
    try:
        resolved = pool._resolve_model_path(repo)
    except FileNotFoundError as e:
        return False, f"FEHLT (nicht aufgeloest): {e}"
    d = Path(resolved)
    problems = []
    has_st = (d / "model.safetensors").is_file() or any(d.glob("*.safetensors"))
    if not has_st:
        problems.append("keine *.safetensors")
    if not (d / "config.json").is_file():
        problems.append("keine config.json")
    if not ((d / "tokenizer.json").is_file()
            or (d / "tokenizer_config.json").is_file()):
        problems.append("keine tokenizer.json/tokenizer_config.json")
    size_mb = _safetensors_size_mb(d) if has_st else 0.0
    if has_st and size_mb < min_mb:
        problems.append(f"safetensors nur {size_mb:.1f} MB "
                        f"(< {min_mb:g} MB, vermutlich unvollstaendig)")
    if problems:
        return False, (f"UNVOLLSTAENDIG: {d} -> " + "; ".join(problems))
    return True, f"OK: {d} ({size_mb:.1f} MB safetensors)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--models-dir", type=Path, default=None,
                    help="Override Modell-Verzeichnis (Default: Runtime-Pfad)")
    ap.add_argument("--min-safetensors-mb", type=float, default=100.0,
                    help="Mindestgroesse model.safetensors in MB (Default 100)")
    ap.add_argument("--all-optional", action="store_true",
                    help="Nur melden; optionale Modelle werden ohnehin "
                         "nicht als Fehler gewertet")
    a = ap.parse_args()

    from app.config import paths
    from app.tts.model_pool import QwenModelPool

    models_dir = a.models_dir or paths.MODELS_DIR

    # Dummy-hw: _resolve_model_path nutzt hw nicht.
    class _NoHW:
        pass

    pool = QwenModelPool(_NoHW(), models_dir=models_dir)

    print(f"MODELL-CHECK (models_dir={models_dir})")
    ok_all = True
    for name in REQUIRED:
        ok, msg = check_one(pool, name, a.min_safetensors_mb)
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {msg}")
        ok_all = ok_all and ok
    for name in OPTIONAL:
        ok, msg = check_one(pool, name, a.min_safetensors_mb)
        print(f"  [{'WARN' if not ok else 'PASS'}] {name} (optional): {msg}")
    tok = models_dir / "Qwen3-TTS-Tokenizer-12Hz"
    print(f"  [INFO] tokenizer-dir: {'gefunden' if tok.is_dir() else 'FEHLT'}"
          f" ({tok})")

    if not ok_all:
        print("MODELL-CHECK FEHLGESCHLAGEN: Pflicht-Modell fehlt oder ist "
              "unvollstaendig. Download: "
              ".venv\\Scripts\\python.exe app\\main.py --download-models "
              "(setzt Teildownloads fort).")
        return 1
    print("MODELL-CHECK OK: alle Pflicht-Modelle vollstaendig.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
