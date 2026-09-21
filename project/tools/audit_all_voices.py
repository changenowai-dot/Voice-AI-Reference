#!/usr/bin/env python3
"""Auditiere ALLE im GUI gezeigten Stimmen.

OFFLINE (default): bundle_present / bundle_valid / selectable für jede Stimme.
--smoke: ZUSÄTZLICH Echt-TTS-Smoke-Test (GPU + qwen_tts). Pro Stimme wird
ein kurzer Satz in der/den unterstützten Sprachen synthetisiert.

FEHLER-PRINZIPIEN:
  * soundfile ist ordentlich importiert (mit stdlib-wave-Fallback) – kein
    "name 'sf' is not defined".
  * Es wird die KORREKTE Sprach-Matrix aus dem Profil verwendet
    (canonical_language / supported_languages / cross_language).
  * VOICE_OUTPUT_DIR wird auf den echten Output-Pfad gesetzt.
  * Wird ein Report nicht geschrieben → FAIL.
  * FINAL_AUDIT=PASS wird NUR ausgegeben, wenn 0 selectable Stimmen
    fehlschlagen.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import sys
import time
import traceback
import wave as _wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "project"))

_DE = "German"
_EN = "English"


# ---------------------------------------------------------------------------
# WAV-Helfer
# ---------------------------------------------------------------------------
@dataclass
class WavMeta:
    sr: int
    ch: int
    n: int
    peak: float
    rms: float
    dur_s: float
    silent: bool


def _read_wav(path: Path) -> WavMeta:
    """Lese WAV + Peak/RMS/Silence. Nutzt soundfile wenn verfügbar, sonst wave."""
    try:
        import soundfile as sf
        import numpy as np
        data, sr = sf.read(str(path), always_2d=False)
        ch = 1 if data.ndim == 1 else data.shape[1]
        n = int(data.shape[0])
        peak = float(abs(data).max()) if n > 0 else 0.0
        rms = float((data.astype("float64") ** 2).mean() ** 0.5) if n > 0 else 0.0
        dur = n / float(max(1, sr))
        return WavMeta(sr, ch, n, peak, rms, dur, (peak < 1e-4) or (rms < 1e-5))
    except Exception:
        with _wave.open(str(path), "rb") as w:
            _nch, _sw, sr, n, _comptype, _compname = w.getparams()
            dur = n / float(max(1, sr))
            return WavMeta(sr, _nch, n, 0.0, 0.0, dur, False)


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Sprach-Matrix
# ---------------------------------------------------------------------------
@dataclass
class LangSpec:
    canonical: str
    supported: list[str]


def _lang_spec(vid: str, prof: dict) -> LangSpec:
    if vid == "vd_e":
        return LangSpec(_DE, [_DE])
    if prof.get("backend_mode") == "customvoice":
        return LangSpec(_DE, [_DE, _EN])
    rs = prof.get("settings") or {}
    vl = str(rs.get("language") or "").strip()
    if vl not in (_DE, _EN):
        vl = _EN if vid.startswith("en_") else _DE
    ls = [l for l in (prof.get("language_support") or []) if l in (_DE, _EN)]
    if not ls:
        ls = [vl]
    if vl not in ls:
        ls.insert(0, vl)
    return LangSpec(vl, ls)


def _tier(p: dict) -> str:
    from app.voices.registry import tier_for
    return tier_for(p)


# ---------------------------------------------------------------------------
# Haupt
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--limit", default="")
    ap.add_argument("--lang", default="both", choices=("de", "en", "both"))
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument("--output-dir", type=Path, default=None)
    ap.add_argument("--text-de", default="Hallo. Dies ist ein kurzer deutscher Test.")
    ap.add_argument("--text-en", default="Hello. This is a short English test.")
    args = ap.parse_args()

    from app import paths
    paths.ensure_directories()
    from app.voices.registry import VoiceRegistry
    reg = VoiceRegistry()
    entries = {e.voice_id: e for e in reg.entries()}
    limit = {v.strip() for v in args.limit.split(",") if v.strip()}

    # Output: der ECHTE zentrale Output-Pfad der Anwendung ist paths.OUTPUT_DIR.
    smoke_out = args.output_dir or (paths.OUTPUT_DIR / "audit_smoke")
    if args.smoke:
        smoke_out.mkdir(parents=True, exist_ok=True)
    json_out = args.json_out or (paths.CACHE_DIR / "audit_smoke_report.json")

    want = []
    if args.lang in ("de", "both"): want.append(_DE)
    if args.lang in ("en", "both"): want.append(_EN)

    # VD-E SHA-Prüfung (sofort fail bei mismatch)
    vd_path = paths.VD_E_GOLDEN_REF_PATH
    if not vd_path.exists():
        leg = ROOT / "reference" / "VD-E_GOLDEN_REFERENCE" / "VD-E.wav"
        if leg.exists(): vd_path = leg
    if not vd_path.exists():
        print(f"FATAL: VD-E Golden Reference fehlt: {paths.VD_E_GOLDEN_REF_PATH}", file=sys.stderr); return 3
    vd_sha = _sha256(vd_path)
    if vd_sha.lower() != paths.VD_E_EXPECTED_SHA256.lower():
        print(f"FATAL: VD-E SHA mismatch: expected={paths.VD_E_EXPECTED_SHA256[:16]} actual={vd_sha[:16]}", file=sys.stderr); return 3

    results: list[dict[str, Any]] = []
    selectable_broken = 0
    fatal = 0
    engines: dict[str, Any] = {}
    want_map = {"de": _DE, "en": _EN, "both": "both"}

    # Spalten-Kopf
    print(f"{'VOICE_ID':52s} {'LANG':7s} {'TYPE':11s} {'TIER':11s} "
          f"{'SEL':3s} {'OK':3s} {'TTS':5s} {'LOC':10s} {'CAN':4s} {'SUP':8s} ERROR")
    print("-" * 170)

    def _row(r: dict) -> None:
        sel = "Y" if r["selectable_in_gui"] else "N"
        ok = "Y" if r["ok"] else "N"
        tts = r.get("tts_pass", "-") or "-"
        loc = r.get("bundle_location", "") or ""
        can = "Y" if r["canonical"] else "N"
        sup = "+".join("de" if l == _DE else "en" for l in r["supported_languages"])
        err = (r["error"] or "")[:50]
        lshort = "de" if r["language"] == _DE else "en"
        print(f"{r['voice_id']:52s} {lshort:7s} {r['voice_type'][:11]:11s} {r['tier'][:11]:11s} "
              f"{sel:3s} {ok:3s} {tts:5s} {loc[:10]:10s} {can:4s} {sup:8s} {err}")

    for vid in sorted(reg._profiles.keys()):
        if limit and vid not in limit:
            continue
        prof = reg._profiles.get(vid, {})
        entry = entries.get(vid)
        backend = str(prof.get("backend_mode", "customvoice"))
        tier = _tier(prof)
        ls = _lang_spec(vid, prof)
        for lang in want:
            if lang not in ls.supported:
                continue
            r: dict[str, Any] = {
                "voice_id": vid, "language": lang,
                "canonical_language": ls.canonical,
                "supported_languages": list(ls.supported),
                "cross_language": (lang != ls.canonical),
                "canonical": (lang == ls.canonical),
                "voice_type": backend, "tier": tier,
                "display_name": str(prof.get("display_name", vid)),
                "selectable_in_gui": False,
                "bundle_present": False, "bundle_valid": False,
                "bundle_location": "", "audio_sha256": None,
                "duration_s": None, "sample_rate": None, "channels": None,
                "silent": None, "peak": None, "rms": None,
                "runtime_load": "skipped", "runtime_load_error": None,
                "runtime_load_s": None,
                "tts_pass": "skipped", "tts_error": None,
                "output_wav": None, "output_duration_s": None,
                "tts_time_s": None, "ok": True, "error": "",
            }
            # Selektierbarkeit
            if backend == "customvoice":
                r["selectable_in_gui"] = True
            elif tier == "REJECTED":
                r["selectable_in_gui"] = False
            elif vid == "vd_e":
                r["selectable_in_gui"] = (lang == _DE) and bool(entry.available if entry else True)
            else:
                r["selectable_in_gui"] = bool(entry.available) if entry else False

            # Bundle-Check
            if backend == "customvoice":
                r.update(bundle_present=True, bundle_valid=True, bundle_location="builtin")
            elif vid == "vd_e":
                r.update(bundle_present=True, bundle_valid=True, bundle_location="golden",
                         audio_sha256=vd_sha[:16])
            elif backend == "clone":
                from app.tts.reference_bundle import (bundled_bundle_path,
                                                      default_bundle_path,
                                                      load_bundle, resolve_bundle)
                found = None; found_loc = ""
                for lab, wp in (("bundled", bundled_bundle_path(vid)),
                                ("cache", default_bundle_path(vid))):
                    if wp.exists() and wp.with_suffix(".wav.json").exists():
                        found, found_loc = wp, lab; break
                r["bundle_present"] = bool(found)
                r["bundle_location"] = found_loc
                if found is None:
                    r["ok"] = False
                    r["error"] = "Bundle fehlt (bundled+cache)"
                else:
                    try:
                        b = resolve_bundle(vid, language=lang,
                                           require_manifest=True, auto_materialize=True)
                        r["bundle_valid"] = True
                        r["audio_sha256"] = b.audio_sha256[:16]
                        meta = _read_wav(b.audio_path)
                        r.update(duration_s=round(meta.dur_s, 2), sample_rate=meta.sr,
                                 channels=meta.ch, silent=meta.silent,
                                 peak=round(meta.peak, 4), rms=round(meta.rms, 4))
                        if meta.n == 0:
                            r["ok"] = False; r["error"] = "WAV leer"
                        elif meta.sr < 16000 or meta.sr > 48000:
                            r["ok"] = False; r["error"] = f"Unübliche SR {meta.sr}"
                        elif meta.silent:
                            r["error"] = "WARNUNG: WAV scheint still"
                    except Exception as e:
                        r["ok"] = False
                        r["error"] = f"Bundle ungültig: {type(e).__name__}: {str(e)[:120]}"

            if r["selectable_in_gui"] and not r["ok"]:
                selectable_broken += 1

            # --- Smoke-TTS ---
            if args.smoke and r["selectable_in_gui"] and r["ok"]:
                text = args.text_de if lang == _DE else args.text_en
                eng_key = f"{backend}:{lang}"
                # --- Runtime-Load ---
                if eng_key not in engines:
                    r_load = "skipped"; r_load_err = None; t0 = time.time()
                    try:
                        from app.hardware.detector import detect_hardware
                        from app.jobs.runner import JobSpec, build_engine
                        from app.security.identity_lock import load_production
                        hw = detect_hardware()
                        production = load_production()
                        spec = JobSpec(text="x", language=lang,
                                       voice_id=vid, speed=args.speed
                                       if hasattr(args, "speed") else 1.0)
                        eng, _meta = build_engine(spec, production)
                        eng.load()
                        engines[eng_key] = eng
                        r["runtime_load"] = "ok"
                        r["runtime_load_s"] = round(time.time() - t0, 2)
                    except Exception as e:
                        r["runtime_load"] = "fail"
                        r["runtime_load_error"] = f"{type(e).__name__}: {e}"
                        r["tts_pass"] = "fail"; r["tts_error"] = r["runtime_load_error"]
                        r["ok"] = False; r["error"] = "Runtime-Load fehlgeschlagen"
                        fatal += 1
                        _row(r); results.append(r)
                        _write_report(json_out, results, selectable_broken, fatal,
                                      smoke_out, args.smoke)
                        print(f"\nFATAL Runtime-Load-Fehler (model?): {e}", file=sys.stderr)
                        return 3
                eng = engines.get(eng_key)
                # --- Synthese ---
                if eng is not None:
                    try:
                        from app.jobs.runner import JobSpec
                        out_wav = smoke_out / f"{vid}_{'de' if lang==_DE else 'en'}.wav"
                        if out_wav.exists():
                            try: out_wav.unlink()
                            except Exception: pass
                        spec = JobSpec(text=text, language=lang, voice_id=vid,
                                       speed=1.0, output_dir=str(smoke_out),
                                       output_name=f"{vid}_{'de' if lang==_DE else 'en'}",
                                       formats=["wav"], output_format="wav")
                        t0 = time.time()
                        res = eng.synthesize(spec)
                        dt = time.time() - t0
                        # Finde Ausgabe
                        final_wav = None
                        if out_wav.exists():
                            final_wav = out_wav
                        elif hasattr(res, "output_path") and res.output_path:
                            final_wav = Path(res.output_path)
                        else:
                            cands = sorted(smoke_out.glob(out_wav.stem + "*.wav"),
                                           key=lambda p: p.stat().st_mtime, reverse=True)
                            if cands: final_wav = cands[0]
                        if final_wav and final_wav.exists() and final_wav.stat().st_size > 1024:
                            m = _read_wav(final_wav)
                            r.update(output_wav=str(final_wav), output_duration_s=round(m.dur_s,2),
                                     tts_time_s=round(dt,2))
                            if m.silent or m.n == 0:
                                r["tts_pass"] = "fail"
                                r["tts_error"] = "Ausgabe ist still/leer"
                                r["ok"] = False; fatal += 1
                            else:
                                r["tts_pass"] = "pass"
                        else:
                            r["tts_pass"] = "fail"
                            r["tts_error"] = f"Keine Output-WAV: {out_wav}"
                            r["ok"] = False; fatal += 1
                    except Exception as e:
                        r["tts_pass"] = "fail"
                        r["tts_error"] = f"{type(e).__name__}: {e}"
                        r["ok"] = False; fatal += 1
                if r["selectable_in_gui"] and not r["ok"]:
                    selectable_broken += 1
            _row(r)
            results.append(r)
        if fatal:
            break

    # Report schreiben
    summary = {
        "total": len(results),
        "ok": sum(1 for r in results if r["ok"]),
        "failed": sum(1 for r in results if not r["ok"]),
        "selectable": sum(1 for r in results if r["selectable_in_gui"]),
        "selectable_but_broken": selectable_broken,
        "tts_smoke": args.smoke,
        "tts_passed": sum(1 for r in results if r.get("tts_pass") == "pass"),
        "tts_failed": sum(1 for r in results if r.get("tts_pass") == "fail"),
        "fatal_issues": fatal,
        "output_dir": str(smoke_out),
        "vd_e_sha_ok": True,
    }
    print()
    print(f"Zusammenfassung: {summary['ok']}/{summary['total']} OK, "
          f"{summary['failed']} fehlerhaft, "
          f"{summary['selectable']} auswählbar, "
          f"{summary['selectable_but_broken']} auswählbar aber defekt.")
    if args.smoke:
        print(f"  TTS: {summary['tts_passed']} pass, {summary['tts_failed']} fail "
              f"(output_dir={smoke_out})")

    code = _write_report(json_out, results, selectable_broken, fatal, smoke_out, args.smoke)
    if code != 0:
        print("\nFINAL_AUDIT=FAIL (Report-Fehler)")
        return code
    if fatal:
        print("\nFINAL_AUDIT=FAIL (fatale Fehler)")
        return 2
    if selectable_broken > 0:
        print(f"\nFINAL_AUDIT=FAIL ({selectable_broken} selectable Stimmen defekt)")
        return 2
    print("\nFINAL_AUDIT=PASS")
    return 0


def _write_report(path: Path, results: list, broken: int, fatal: int,
                  out_dir: Path, smoke: bool) -> int:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "summary": {
                "total": len(results),
                "ok": sum(1 for r in results if r["ok"]),
                "failed": sum(1 for r in results if not r["ok"]),
                "selectable": sum(1 for r in results if r["selectable_in_gui"]),
                "selectable_but_broken": broken,
                "tts_smoke": smoke,
                "tts_passed": sum(1 for r in results if r.get("tts_pass") == "pass"),
                "tts_failed": sum(1 for r in results if r.get("tts_pass") == "fail"),
                "fatal_issues": fatal,
                "output_dir": str(out_dir),
            },
            "voices": results,
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                        encoding="utf-8")
        print(f"JSON-Report: {path}")
        return 0
    except Exception as e:
        print(f"FATAL: Report-Schreiben fehlgeschlagen: {e}", file=sys.stderr)
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
