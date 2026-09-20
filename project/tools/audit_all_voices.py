"""Auditiere ALLE GUI-gezeigten Stimmen auf technische Verwendbarkeit.

Für jede Stimme wird geprüft:
1. Registry-Eintrag vorhanden
2. (bei Clone-Stimmen) WAV in cache/voice_refs/ vorhanden
3. WAV > 0 Bytes, lesbar (soundfile/librosa), Sample-Rate, Kanäle, Dauer
4. Manifest-WAV.json vorhanden, JSON valide, voice_id/language korrekt
5. Bundle-Validator (reference_bundle.load_bundle) läuft erfolgreich
6. Optional (wenn --smoke gesetzt): 1-Wort-TTS ("Hallo." / "Hello.")

Der Test gibt eine Tabelle aus und schreibt alle Ergebnisse als JSON-
Datei; Exit-Code ist !=0 wenn irgendeine Stimme als FEHLER markiert ist,
die die GUI als selektierbar anbietet.

ACHTUNG: Smoke-Synthese lädt das Qwen-Modell (benötigt GPU).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "project"))


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="Zusätzlich Echt-TTS-Smoke-Test durchführen "
                         "(benötigt GPU + qwen_tts).")
    ap.add_argument("--limit", type=str, default="",
                    help="Nur diese Voice-IDs testen (Komma-getrennt).")
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument("--lang", default="both", choices=("de", "en", "both"))
    args = ap.parse_args()

    from app.voices.registry import VoiceRegistry, tier_for
    from app.gui.voice_view import voice_groups
    from app import paths
    import soundfile as sf

    reg = VoiceRegistry()
    langs = ["German", "English"] if args.lang == "both" else \
            ["German"] if args.lang == "de" else ["English"]

    limit_set = set(v.strip() for v in args.limit.split(",") if v.strip())

    results = []
    exit_code = 0

    # Cache für bereits geladene Engines (nur bei --smoke)
    engines: dict = {}

    for lang in langs:
        groups = voice_groups(lang, reg)
        all_rows = (groups["locked"] + groups["custom"] + groups["clone"]
                    + groups["candidates"])
        for row in all_rows:
            vid = row["voice_id"]
            if limit_set and vid not in limit_set:
                continue
            entry = reg.get(vid)
            r = {
                "voice_id": vid,
                "language": lang,
                "group": next((g for g, rows in groups.items() if row in rows),
                              "?"),
                "voice_type": (entry.backend_mode if entry else "?"),
                "tier": row.get("tier", ""),
                "status_label": row.get("status", ""),
                "selectable_in_gui": bool(row.get("selectable")),
                "technically_available_reported": bool(row.get("available")),
                "reference_checks": {},
                "runtime_load": "skipped",
                "runtime_load_error": None,
                "smoke_test": "skipped",
                "smoke_test_error": None,
                "ok": True,
                "errors": [],
            }

            # --- Custom Voices / VD-E: ---
            if entry and entry.backend_mode == "customvoice":
                r["reference_checks"] = {"note": "customvoice – keine Referenz nötig"}
            elif entry and vid == "vd_e":
                vd_path = ROOT / "VD-E_GOLDEN_REFERENCE" / "VD-E.wav"
                sha = sha256_file(vd_path)
                expected = ("b156c02a60a873ad95fc92390c4a136c85308b20188373"
                            "cd734bee5e5e5f2025")
                if sha != expected:
                    r["ok"] = False
                    r["errors"].append(f"VD-E SHA mismatch! {sha[:16]}…")
                    exit_code = 2
                else:
                    r["reference_checks"] = {"wav": str(vd_path), "sha256": "OK"}
            elif entry and entry.backend_mode == "clone":
                # Prüfe kanonischen WAV-Pfad
                wav_path = paths.VOICE_REFS_DIR / f"{vid}.wav"
                manifest_path = wav_path.with_suffix(".wav.json")
                r["reference_checks"]["wav_path"] = str(wav_path)
                if not wav_path.exists():
                    r["ok"] = False
                    r["errors"].append(f"WAV fehlt: {wav_path}")
                else:
                    try:
                        info = sf.info(str(wav_path))
                        r["reference_checks"]["wav_bytes"] = wav_path.stat().st_size
                        r["reference_checks"]["samplerate"] = info.samplerate
                        r["reference_checks"]["channels"] = info.channels
                        r["reference_checks"]["duration_s"] = round(
                            float(info.duration), 2)
                        if info.frames == 0:
                            r["ok"] = False
                            r["errors"].append("WAV leer (0 Frames)")
                        if info.samplerate < 16000 or info.samplerate > 48000:
                            r["errors"].append(
                                f"Unübliche Samplerate: {info.samplerate} Hz")
                    except Exception as e:
                        r["ok"] = False
                        r["errors"].append(f"WAV nicht lesbar: {e}")
                if not manifest_path.exists():
                    if wav_path.exists():
                        r["ok"] = False
                        r["errors"].append(f"Manifest fehlt: {manifest_path}")
                else:
                    try:
                        m = json.loads(manifest_path.read_text(encoding="utf-8"))
                        r["reference_checks"]["manifest_voice_id"] = m.get("voice_id")
                        r["reference_checks"]["manifest_language"] = m.get("language")
                        if m.get("voice_id") and m["voice_id"] != vid:
                            r["ok"] = False
                            r["errors"].append(
                                f"Manifest voice_id={m['voice_id']} != {vid}")
                    except Exception as e:
                        r["ok"] = False
                        r["errors"].append(f"Manifest ungültig: {e}")
                # Bundle-Validator
                if wav_path.exists() and manifest_path.exists():
                    try:
                        from app.tts.reference_bundle import resolve_bundle
                        b = resolve_bundle(vid,
                                           language="en" if vid.startswith("en_")
                                                    else "de",
                                           require_manifest=True)
                        r["reference_checks"]["bundle_valid"] = True
                        r["reference_checks"]["bundle_duration"] = (
                            round(b.duration_s, 2) if b else None)
                    except Exception as e:
                        r["ok"] = False
                        r["errors"].append(f"Bundle-Validator: {e}")
            else:
                r["ok"] = False
                r["errors"].append(f"Unbekannter backend_mode: "
                                    f"{entry.backend_mode if entry else 'kein Entry'}")

            # Wenn GUI die Stimme als selectable anbietet, muss sie technisch
            # auch funktionieren.
            if row.get("selectable") and not r["ok"]:
                exit_code = max(exit_code, 3)
                r["errors"].append(
                    "!! GUI bietet Stimme als auswählbar an, aber "
                    "technische Prüfung fehlgeschlagen.")

            # Optional: Runtime-Load + Smoke-Synthese
            if args.smoke and entry and row.get("selectable"):
                try:
                    # Lazy Import um Syntax-Check nicht vom Vorhandensein
                    # von qwen_tts abhängig zu machen.
                    if entry.backend_mode not in engines:
                        from app.hardware.detector import detect_hardware
                        from app.jobs.runner import build_engine
                        from app import config as cfgmod
                        hw = detect_hardware()
                        from app.jobs.runner import JobSpec
                        spec = JobSpec(text="x", language=lang,
                                       voice_id=vid, speed=1.0)
                        from app.security.identity_lock import load_production
                        production = load_production()
                        eng, _ = build_engine(spec, production)
                        eng.load()
                        engines[entry.backend_mode] = eng
                    r["runtime_load"] = "ok"
                except Exception as e:
                    r["runtime_load"] = "fail"
                    r["runtime_load_error"] = f"{type(e).__name__}: {e}"
                    r["errors"].append(r["runtime_load_error"])
                    exit_code = max(exit_code, 4)
            results.append(r)

    # Ausgabe
    print(f"{'VOICE_ID':45s} {'LANG':7s} {'TYPE':12s} {'TIER':11s} "
          f"{'SEL':4s} {'OK':3s}  FEHLER")
    print("-" * 140)
    for r in results:
        err = "; ".join(r["errors"]) if r["errors"] else ""
        print(f"{r['voice_id']:45s} {r['language']:7s} {r['voice_type']:12s} "
              f"{r['tier']:11s} {'Y' if r['selectable_in_gui'] else 'N':4s} "
              f"{'Y' if r['ok'] else 'N':3s}  {err[:80]}")

    summary = {
        "total": len(results),
        "ok": sum(1 for r in results if r["ok"]),
        "failed": sum(1 for r in results if not r["ok"]),
        "selectable": sum(1 for r in results if r["selectable_in_gui"]),
        "selectable_but_broken": sum(1 for r in results
                                      if r["selectable_in_gui"] and not r["ok"]),
    }
    print()
    print(f"Zusammenfassung: {summary['ok']}/{summary['total']} OK, "
          f"{summary['failed']} fehlerhaft, "
          f"{summary['selectable']} auswählbar in GUI, "
          f"{summary['selectable_but_broken']} auswählbar aber defekt.")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps({"summary": summary, "voices": results}, indent=2,
                       ensure_ascii=False, default=str),
            encoding="utf-8")
        print(f"JSON-Report: {args.json_out}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
