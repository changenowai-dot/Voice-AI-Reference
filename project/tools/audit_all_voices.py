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


class _WavInfo:
    def __init__(self, samplerate: int, channels: int, frames: int, duration: float):
        self.samplerate = samplerate
        self.channels = channels
        self.frames = frames
        self.duration = duration


def _wav_info(path: Path):
    """Lese WAV-Metadaten mit soundfile (falls verfügbar) oder stdlib wave."""
    if sf is not None:
        return sf.info(str(path))
    with _wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        nframes = w.getnframes()
    dur = nframes / float(max(1, sr))
    return _WavInfo(sr, ch, nframes, dur)


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
    from app import paths
    try:
        import soundfile as sf
    except Exception:
        sf = None   # Fallback: wave-Modul für reine WAV-Lesbarkeitsprüfung
    import wave as _wave

    reg = VoiceRegistry()
    langs = ["German", "English"] if args.lang == "both" else \
            ["German"] if args.lang == "de" else ["English"]

    limit_set = set(v.strip() for v in args.limit.split(",") if v.strip())

    # Baue alle Voice-IDs und ihre GUI-Eigenschaften nach, ohne tkinter zu
    # importieren (damit das Audit auch auf Headless-Systemen / ohne GUI
    # laufen kann). Die Selektierbarkeits-Logik ist identisch mit
    # app/gui/voice_view.py (dort kommentiert).
    all_vids = list(reg._profiles.keys())

    def _voice_lang_for(vid: str, prof: dict) -> str:
        rs = prof.get("settings") or {}
        vl = str(rs.get("language") or "").strip()
        if vl in ("English", "German"):
            return vl
        if vid.startswith("en_"):
            return "English"
        return "German"

    def _group_for(vid: str, prof: dict, lang: str, selectable: bool) -> str:
        if vid == "vd_e":
            return "locked"
        if prof.get("backend_mode") == "customvoice":
            return "custom"
        t = tier_for(prof)
        if t == "REJECTED":
            return "candidates"
        return "clone" if selectable else "candidates"

    # Einträge vorberechnen (registry.entries() löst Verfügbarkeit auf).
    entries_by_id = {e.voice_id: e for e in reg.entries()}

    results = []
    exit_code = 0
    engines: dict = {}

    for lang in langs:
        for vid in all_vids:
            if limit_set and vid not in limit_set:
                continue
            prof = reg._profiles.get(vid, {})
            vl = _voice_lang_for(vid, prof)
            # Pro Sprach-Modus filtern: VD-E nur Deutsch; andere nur wenn
            # language_support die Sprache enthält ODER es ihre native
            # Sprache ist ODER sie CustomVoice sind.
            if vid == "vd_e" and lang != "German":
                continue
            if prof.get("backend_mode") == "clone":
                ls = prof.get("language_support") or []
                if lang not in ls and vl != lang:
                    continue
            entry = entries_by_id.get(vid)
            t = tier_for(prof)
            if prof.get("backend_mode") == "customvoice":
                tech_avail = True
            elif t == "REJECTED":
                tech_avail = False
            else:
                tech_avail = bool(entry.available) if entry else False
            # Selectable = tier != REJECTED & (customvoice | (clone & tech_avail))
            if vid == "vd_e":
                selectable = (lang == "German") and tech_avail
            elif t == "REJECTED":
                selectable = False
            elif prof.get("backend_mode") == "customvoice":
                selectable = True
            else:
                selectable = tech_avail
            group = _group_for(vid, prof, lang, selectable)
            tier_label = {"ACTIVE": "PRODUKTION", "BACKUPS": "ARCHIV",
                          "UNASSESSED": "KANDIDAT", "REJECTED": "ZURÜCKGEWIESEN"}.get(t, t)
            r = {
                "voice_id": vid,
                "language": lang,
                "group": group,
                "voice_type": (prof.get("backend_mode", "?")),
                "tier": t,
                "status_label": tier_label,
                "selectable_in_gui": selectable,
                "technically_available_reported": tech_avail,
                "reference_checks": {},
                "runtime_load": "skipped",
                "runtime_load_error": None,
                "tts_pass": "skipped",     # "pass"/"fail"/"skipped"
                "tts_error": None,
                "output_wav": None,
                "duration": None,
                "ok": True,
                "errors": [],
                "bundle_present": False,
                "bundle_valid": False,
                "bundle_location": "none",
                "audio_sha256": None,
            }

            # --- Custom Voices / VD-E: ---
            if entry and entry.backend_mode == "customvoice":
                r["reference_checks"] = {"note": "customvoice – keine Referenz nötig"}
            elif entry and vid == "vd_e":
                vd_path = paths.VD_E_GOLDEN_REF_PATH
                if not vd_path.exists():
                    legacy = ROOT / "reference" / "VD-E_GOLDEN_REFERENCE" / "VD-E.wav"
                    if legacy.exists():
                        vd_path = legacy
                if not vd_path.exists():
                    r["ok"] = False
                    r["errors"].append(f"VD-E Golden Reference FEHLT: {paths.VD_E_GOLDEN_REF_PATH}")
                    exit_code = 2
                else:
                    sha = sha256_file(vd_path)
                    expected = paths.VD_E_EXPECTED_SHA256
                    if sha != expected:
                        r["ok"] = False
                        r["errors"].append(f"VD-E SHA mismatch! erwartet={expected[:16]}… erhalten={sha[:16]}…")
                        exit_code = 2
                    else:
                        r["reference_checks"] = {"wav": str(vd_path), "sha256": "OK"}
                        r["bundle_present"] = True
                        r["bundle_valid"] = True
                        r["bundle_location"] = "golden"
            elif entry and entry.backend_mode == "clone":
                # Suche das Bundle in der Reihenfolge der Release-Priorität:
                #   (1) release-bundled  project/app/voices/bundles/
                #   (2) runtime-cache    project/cache/voice_refs/
                # Ein Fehlen in BEIDEN ist ein echter Fehler, wenn die
                # Stimme als selectable angeboten wird.
                from app.tts.reference_bundle import (
                    bundled_bundle_path, default_bundle_path,
                    load_bundle, resolve_bundle,
                )
                # ``lang`` enthält bereits die äussere Loop-Sprache
                # ("German"/"English"); wir brauchen KEINE Neuzuweisung
                # die die Loop-Variable überschreibt.
                voice_lang = lang
                candidates = [("bundled", bundled_bundle_path(vid)),
                              ("cache", default_bundle_path(vid))]
                found_loc = None
                found_wav = None
                for label, wp in candidates:
                    if wp.exists() and wp.with_suffix(".wav.json").exists():
                        found_loc, found_wav = label, wp; break
                r["bundle_present"] = bool(found_wav)
                r["bundle_location"] = found_loc or "none"
                if found_wav is None:
                    # VD-E-Ausnahme: Golden Reference
                    if vid == "vd_e" and (ROOT / "VD-E_GOLDEN_REFERENCE" / "VD-E.wav").exists():
                        found_loc, found_wav = "golden", ROOT / "VD-E_GOLDEN_REFERENCE" / "VD-E.wav"
                if found_wav is None:
                    r["ok"] = False
                    r["errors"].append(
                        f"WAV fehlt (weder gebündelt noch im Cache): "
                        f"{bundled_bundle_path(vid)} / {default_bundle_path(vid)}")
                    r["reference_checks"]["bundled_wav"] = str(bundled_bundle_path(vid))
                    r["reference_checks"]["cache_wav"] = str(default_bundle_path(vid))
                else:
                    wav_path = found_wav
                    manifest_path = wav_path.with_suffix(".wav.json")
                    r["reference_checks"]["wav_path"] = str(wav_path)
                    r["reference_checks"]["location"] = found_loc
                    try:
                        info = _wav_info(wav_path)
                        r["reference_checks"]["wav_bytes"] = wav_path.stat().st_size
                        r["reference_checks"]["samplerate"] = info.samplerate
                        r["reference_checks"]["channels"] = info.channels
                        r["reference_checks"]["duration_s"] = round(float(info.duration), 2)
                        r["duration"] = round(float(info.duration), 2)
                        if info.frames == 0:
                            r["ok"] = False
                            r["errors"].append("WAV leer (0 Frames)")
                        if info.samplerate < 16000 or info.samplerate > 48000:
                            r["errors"].append(f"Unübliche Samplerate: {info.samplerate} Hz")
                    except Exception as e:
                        r["ok"] = False
                        r["errors"].append(f"WAV nicht lesbar: {e}")
                    if manifest_path.exists():
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
                # Bundle-Validator (ohne Cache-Materialisierung bei reinem
                # Check) — nutzt resolve_bundle das zuerst im Bundled-Ordner
                # sucht.
                try:
                    b = resolve_bundle(vid, language=voice_lang,
                                       require_manifest=(vid != "vd_e"),
                                       auto_materialize=(found_loc != "bundled"))
                    r["reference_checks"]["bundle_valid"] = True
                    r["bundle_valid"] = True
                    r["audio_sha256"] = b.audio_sha256[:16] + "…"
                except Exception as e:
                    r["ok"] = False
                    r["bundle_valid"] = False
                    r["errors"].append(f"Bundle-Validator: {e}")
            else:
                r["ok"] = False
                r["errors"].append(f"Unbekannter backend_mode: "
                                    f"{entry.backend_mode if entry else 'kein Entry'}")

            # Wenn GUI die Stimme als selectable anbietet, muss sie technisch
            # auch funktionieren.
            if selectable and not r["ok"]:
                exit_code = max(exit_code, 3)
                r["errors"].append(
                    "!! GUI bietet Stimme als auswählbar an, aber "
                    "technische Prüfung fehlgeschlagen.")

            # Optional: Runtime-Load + Smoke-Synthese (ECHTER TTS-TEST)
            if args.smoke and entry and selectable:
                out_dir = paths.VOICE_OUTPUT_DIR / "audit_smoke"
                out_dir.mkdir(parents=True, exist_ok=True)
                smoke_text = ("Hallo. Dies ist ein kurzer deutscher Test."
                              if lang == "German"
                              else "Hello. This is a short English test.")
                try:
                    if entry.backend_mode not in engines:
                        from app.hardware.detector import detect_hardware
                        from app.jobs.runner import build_engine, JobSpec
                        from app.security.identity_lock import load_production
                        hw = detect_hardware()
                        production = load_production()
                        # Nur Engine bauen und laden (noch nicht synthetisieren).
                        spec = JobSpec(text="x", language=lang,
                                       voice_id="vd_e" if entry.backend_mode == "voicedesign"
                                                else (entry.speaker_name or vid),
                                       speed=1.0)
                        # Spezialfall: wir bauen pro backend_mode + sprache
                        eng_key = f"{entry.backend_mode}:{lang}"
                        if eng_key not in engines:
                            eng, _ = build_engine(spec, production)
                            eng.load()
                            engines[eng_key] = eng
                    r["runtime_load"] = "ok"
                except Exception as e:
                    r["runtime_load"] = "fail"
                    r["runtime_load_error"] = f"{type(e).__name__}: {e}"
                    r["tts_pass"] = "fail"
                    r["tts_error"] = r["runtime_load_error"]
                    r["errors"].append(r["runtime_load_error"])
                    exit_code = max(exit_code, 4)
                    results.append(r); continue
                try:
                    from app.jobs.runner import JobSpec
                    import tempfile
                    eng_key = f"{entry.backend_mode}:{lang}"
                    eng = engines[eng_key]
                    # Tatsächliche Kurzsynthese
                    out_wav = out_dir / f"{vid}_{lang}.wav"
                    spec = JobSpec(text=smoke_text, language=lang,
                                   voice_id=vid, speed=1.0,
                                   output_path=str(out_wav))
                    t0 = time.time()
                    eng.synthesize(spec, on_progress=lambda *a, **k: None)
                    dt = time.time() - t0
                    if out_wav.exists() and out_wav.stat().st_size > 1024:
                        try:
                            info = _wav_info(out_wav)
                            r["duration"] = round(float(info.duration), 2)
                        except Exception:
                            pass
                        r["tts_pass"] = "pass"
                        r["output_wav"] = str(out_wav)
                        r["tts_time_s"] = round(dt, 2)
                    else:
                        r["tts_pass"] = "fail"
                        r["tts_error"] = f"Keine Output-WAV erzeugt ({out_wav})"
                        r["errors"].append(r["tts_error"])
                        exit_code = max(exit_code, 5)
                except Exception as e:
                    r["tts_pass"] = "fail"
                    r["tts_error"] = f"{type(e).__name__}: {e}"
                    r["errors"].append(r["tts_error"])
                    exit_code = max(exit_code, 5)
            results.append(r)

    # Ausgabe
    print(f"{'VOICE_ID':52s} {'LANG':7s} {'TYPE':12s} {'TIER':11s} "
          f"{'SEL':4s} {'OK':3s} {'LOC':10s}  FEHLER")
    print("-" * 150)
    for r in results:
        err = "; ".join(r["errors"]) if r["errors"] else ""
        lang_short = "de" if r["language"] == "German" else (
            "en" if r["language"] == "English" else r["language"])
        print(f"{r['voice_id']:52s} {lang_short:7s} {r['voice_type']:12s} "
              f"{r['tier']:11s} {'Y' if r['selectable_in_gui'] else 'N':4s} "
              f"{'Y' if r['ok'] else 'N':3s} "
              f"{r.get('bundle_location',''):10s}  {err[:70]}")

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
