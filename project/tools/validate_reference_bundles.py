#!/usr/bin/env python3
"""Validate the full voice catalogue and reference-bundle distribution.

Prüft jede im Registry vorhandene Stimme (VD-E, CustomVoice, ACTIVE Clone,
BACKUPS, UNASSESSED, REJECTED) und erzeugt einen strukturierten Report,
der folgende Fragen beantwortet:

  * Ist die Stimme im GUI auswählbar (selectable)?
  * Falls nein: was ist der eindeutige technische oder produktions-
    bezogene Grund?
  * Falls ja: ist das Referenz-Bundle vorhanden (gebündelt ODER im
    Cache) und valide?
  * VD-E: SHA der Golden Reference intakt?

Exit-Code:
  0 – alles konsistent (kann aber fehlende optionale/archivierte
      Bundles melden, ohne zu failen).
  1 – mindestens eine ACTIVE/Pflicht-Produktionsstimme fehlt oder
      ein Bundle ist ungültig.
  2 – VD-E Golden Reference SHA mismatch oder fehlt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "project"))

from app import paths                                           # noqa: E402
from app.tts.reference_bundle import (                          # noqa: E402
    bundled_bundle_path,
    bundle_exists,
    default_bundle_path,
    load_bundle,
    manifest_path_for,
    sha256_file,
)
from app.voices.registry import VoiceRegistry, tier_for         # noqa: E402


@dataclass
class VoiceReport:
    voice_id: str
    display_name: str
    backend_mode: str                  # customvoice | clone
    tier: str                          # ACTIVE | BACKUPS | UNASSESSED | REJECTED
    gender: str
    language: str
    production_locked: bool
    selectable: bool
    non_selectable_reason: str = ""
    bundle_present: bool = False
    bundle_location: str = ""          # bundled | cache | golden | none
    bundle_valid: bool = False
    bundle_error: str = ""
    audio_sha: str = ""
    duration_s: float | None = None
    sample_rate: int | None = None


def _ok(s: str) -> str: return f"\033[32m[OK]\033[0m  {s}"
def _warn(s: str) -> str: return f"\033[33m[!]\033[0m   {s}"
def _fail(s: str) -> str: return f"\033[31m[!!]\033[0m  {s}"


def _check_vd_e_golden() -> tuple[bool, str, dict[str, Any]]:
    p = paths.VD_E_GOLDEN_REF_PATH
    if not p.exists():
        p2 = ROOT / "reference" / "VD-E_GOLDEN_REFERENCE" / "VD-E.wav"
        if p2.exists():
            p = p2
        else:
            return False, f"FEHLT: {paths.VD_E_GOLDEN_REF_PATH}", {"path": str(p)}
    actual = sha256_file(p)
    if actual.lower() != paths.VD_E_EXPECTED_SHA256.lower():
        return False, (f"SHA-ABWEICHUNG erwartet={paths.VD_E_EXPECTED_SHA256[:16]}… "
                       f"actual={actual[:16]}…"), {"path": str(p), "actual": actual}
    return True, f"VD-E Golden Reference OK  sha={actual[:16]}…", {"path": str(p), "sha": actual}


def _detect_selectability(backend: str, tier: str,
                          vid: str, language: str,
                          available_flag: bool | None) -> tuple[bool, str]:
    """See voice_view.py logic: customvoice immer selektierbar; REJECTED
    nie; clone benötigt technische Verfügbarkeit UND tier != REJECTED;
    vd_e nur in German.
    """
    if backend == "customvoice":
        return True, ""
    if tier == "REJECTED":
        return False, "REJECTED – menschlich abgelehnt, nicht auswählbar."
    if vid == "vd_e" and language != "German":
        return False, "VD-E nur in Deutsch auswählbar (Golden Reference ist Deutsch)."
    if available_flag is False:
        return False, "nicht selektierbar (available=false im Profil)."
    return True, ""


def _bundle_status(vid: str, language: str) -> VoiceReport:
    present, reason = bundle_exists(vid, language=language)
    loc = ""
    sha = ""
    dur: float | None = None
    sr: int | None = None
    valid = False
    err = reason if not present else ""
    if present:
        for label, wav in (("bundled", bundled_bundle_path(vid)),
                           ("cache", default_bundle_path(vid))):
            if wav.exists():
                b = load_bundle(wav, voice_id=vid, expected_language=language)
                if b is not None:
                    okv, _sum, det = b.validate()
                    if okv:
                        loc = label
                        sha = b.audio_sha256
                        dur = det.get("duration_s")
                        sr = det.get("sample_rate")
                        valid = True
                        break
                    err = _sum
        if not valid and not err:
            err = reason
    return VoiceReport(
        voice_id=vid, display_name="", backend_mode="clone",
        tier="", gender="", language=language, production_locked=False,
        selectable=False, bundle_present=present, bundle_location=loc,
        bundle_valid=valid, bundle_error=err, audio_sha=sha,
        duration_s=dur, sample_rate=sr,
    )


def inventory() -> list[VoiceReport]:
    reg = VoiceRegistry()
    out: list[VoiceReport] = []
    for vid, prof in reg._profiles.items():
        backend = str(prof.get("backend_mode", "customvoice"))
        t = tier_for(prof)
        raw_settings = prof.get("settings") or {}
        vl = str(raw_settings.get("language") or "").strip()
        if vl not in ("English", "German"):
            vl = ("English" if vid.startswith("en_") else "German")
        # Technische Verfügbarkeit via bundle_exists (ohne Seiteneffekt).
        available_flag = prof.get("available")
        if backend == "customvoice":
            tech_avail = True
            berr = ""
            present = True
            valid = True
            loc = "builtin"
            sha = ""; dur = None; sr = None
        elif t == "REJECTED":
            tech_avail = False; berr = "REJECTED"; present = False; valid = False
            loc = ""; sha = ""; dur = None; sr = None
        else:
            bs = _bundle_status(vid, vl)
            tech_avail = bs.bundle_valid
            berr = bs.bundle_error
            present = bs.bundle_present
            valid = bs.bundle_valid
            loc = bs.bundle_location
            sha = bs.audio_sha; dur = bs.duration_s; sr = bs.sample_rate
        selectable, reason = _detect_selectability(
            backend, t, vid, vl, available_flag)
        if selectable and not tech_avail:
            selectable = False
            reason = f"nicht selektierbar – Bundle fehlt oder ungültig: {berr[:100]}"
        out.append(VoiceReport(
            voice_id=vid,
            display_name=str(prof.get("display_name", vid)),
            backend_mode=backend,
            tier=t,
            gender=str(prof.get("gender", "")),
            language=vl,
            production_locked=bool(prof.get("production_locked", False)),
            selectable=selectable,
            non_selectable_reason=reason,
            bundle_present=present and (backend == "clone"),
            bundle_location=loc if backend == "clone" else ("builtin" if backend == "customvoice" else ""),
            bundle_valid=valid if backend == "clone" else True,
            bundle_error=berr if (backend == "clone" and not valid) else "",
            audio_sha=sha, duration_s=dur, sample_rate=sr,
        ))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fail-on-missing-active", action="store_true",
                    default=True,
                    help="Exit 1 wenn eine ACTIVE/Pflicht-Stimme fehlt (default: an).")
    ap.add_argument("--json", default=None, help="Schreibe JSON-Report hierhin.")
    ap.add_argument("--show-all", action="store_true",
                    help="Zeige auch CustomVoice + REJECTED im Text-Report.")
    args = ap.parse_args()

    vd_ok, vd_msg, vd_det = _check_vd_e_golden()
    print(_ok(vd_msg) if vd_ok else _fail(vd_msg))

    reports = inventory()

    # Sortierung: vd_e, ACTIVE DE, ACTIVE EN, BACKUPS, UNASSESSED, REJECTED, customvoice
    def _sort_key(r: VoiceReport):
        order = {"ACTIVE": 0, "BACKUPS": 1, "UNASSESSED": 2, "REJECTED": 3}
        return (order.get(r.tier, 9), 0 if r.language == "German" else 1,
                r.voice_id)
    reports.sort(key=_sort_key)

    counts = {"ACTIVE": 0, "BACKUPS": 0, "UNASSESSED": 0, "REJECTED": 0,
              "customvoice": 0}
    missing_active: list[str] = []
    invalid: list[str] = []
    print()
    print(f"{'VOICE-ID':55s} {'TIER':10s} {'SEL':4s} {'BUNDLE':10s} {'DUR':>6s}  DETAIL")
    print("-" * 130)
    for r in reports:
        if r.backend_mode == "customvoice":
            counts["customvoice"] += 1
            if not args.show_all:
                continue
        else:
            counts[r.tier] = counts.get(r.tier, 0) + 1
        sel = "YES" if r.selectable else "no"
        bl = f"{r.bundle_location or '-':10s}"
        dur = f"{r.duration_s:5.1f}s" if r.duration_s else "   -  "
        if r.selectable and r.bundle_valid:
            line = _ok(f"{r.voice_id:55s} {r.tier:10s} {sel:4s} {bl} {dur}")
        elif r.tier == "REJECTED":
            line = _warn(f"{r.voice_id:55s} {r.tier:10s} {sel:4s} {bl} {dur}  {r.non_selectable_reason}")
        elif not r.bundle_present and r.backend_mode == "clone":
            line = _fail(f"{r.voice_id:55s} {r.tier:10s} {sel:4s} FEHLT     {dur}")
            if r.tier == "ACTIVE":
                missing_active.append(r.voice_id)
        elif not r.bundle_valid:
            line = _fail(f"{r.voice_id:55s} {r.tier:10s} {sel:4s} UNGÜLTIG  {dur}  {r.bundle_error[:80]}")
            invalid.append(r.voice_id)
        else:
            line = f"     {r.voice_id:55s} {r.tier:10s} {sel:4s} {bl} {dur}"
        print(line)

    print()
    print("Zusammenfassung:")
    print(f"  VD-E Golden:        {'OK' if vd_ok else 'FEHLER'}")
    print(f"  CustomVoice (builtin): {counts.get('customvoice',0)}")
    for t in ("ACTIVE", "BACKUPS", "UNASSESSED", "REJECTED"):
        print(f"  {t:10s}: {counts.get(t,0)}")
    print(f"  Fehlende ACTIVE:    {len(missing_active)}")
    print(f"  Ungültige Bundles:  {len(invalid)}")

    if args.json:
        payload = {
            "vd_e_golden": {"ok": vd_ok, "detail": vd_msg, **vd_det},
            "voices": [asdict(r) for r in reports],
            "counts": counts,
            "missing_active": missing_active,
            "invalid": invalid,
        }
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                                   encoding="utf-8")
        print(f"\nJSON-Report: {args.json}")

    if not vd_ok:
        return 2
    if missing_active or invalid:
        if args.fail_on_missing_active:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
