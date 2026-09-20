#!/usr/bin/env python3
"""Import reference bundles from the local runtime-cache into the versioned
release-bundle folder (``project/app/voices/bundles/``).

Zweck
-----
Die auf dem GPU-/Arbeits-Host einmalig materialisierten Referenz-WAVs
(``project/cache/voice_refs/<id>.wav`` + ``<id>.wav.json``) werden
BITGENAU in das versionierte Bundle-Verzeichnis kopiert, damit sie mit
``git commit`` + ``git archive`` im Release landen. Das Skript:

  1. findet zu jeder Ziel-Stimme die WAV im Source-Cache,
  2. lädt das zugehörige .wav.json-Manifest (Sidecar),
  3. erzeugt/repariert das Manifest ggf. aus ``voice_generation_recipes.json``
     (nur, wenn das fehlende Manifest kanonisch beweisbar ist),
  4. validiert das Bundle auf: WAV-lesbar, Sample-Rate, Dauer 2–60s,
     Audio-SHA256, Text-SHA256, Sprache,
  5. kopiert WAV + Manifest ATOMAR nach ``project/app/voices/bundles/``,
  6. verifiziert SHA256 nach dem Kopieren (bitgenau),
  7. erzeugt einen abschliessenden Report (Text + JSON).

Vorbereitetes Beispiel auf dem Windows-Host (nach erfolgreichem
materialize_references.py Lauf mit funktionierenden Referenzen)::

    python project/tools/import_voice_bundles.py --from-cache --all

Das Skript braucht KEINE GPU und KEINE Modelle – es arbeitet rein
dateibasiert und ist idempotent. Bereits importierte Bundles mit
gleichem SHA werden als UNVERÄNDERT gemeldet und nicht überschrieben.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "project"))

from app import paths                                           # noqa: E402
from app.tts.reference_bundle import (                          # noqa: E402
    BUNDLE_MANIFEST_SUFFIX,
    bundled_bundle_path,
    default_bundle_path,
    load_bundle,
    manifest_path_for,
    sha256_file,
    write_bundle_atomically,
)
from app.voices.registry import VoiceRegistry                   # noqa: E402


# ---------------------------------------------------------------------------
def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m"


def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m"


def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m"


# ---------------------------------------------------------------------------
# Target selection
# ---------------------------------------------------------------------------
def _target_voices(*, voice_id: str | None, scope: str) -> list[str]:
    """Collect target voice_ids according to --scope / --voice-id.

    scope in:
      * "production" (default)  – ACTIVE clone voices (Pflicht-Produktion)
      * "all-clone"             – alle clone-Stimmen (ACTIVE, BACKUPS,
                                  UNASSESSED) ausser REJECTED. Nützlich
                                  um auch Archiv-/Kandidatenstimmen zu
                                  importieren.
      * "listed"                – nur die per --voice-id angegebenen.
    """
    reg = VoiceRegistry()
    out: list[str] = []
    for vid, prof in reg._profiles.items():
        if prof.get("backend_mode") != "clone":
            continue
        if vid == "vd_e":
            # VD-E wird nie in bundles/ kopiert – Golden Reference
            # verbleibt in project/VD-E_GOLDEN_REFERENCE/.
            continue
        status = str(prof.get("status") or "").lower()
        rejected = "rejected" in status
        if scope == "production":
            # ACTIVE only
            from app.voices.registry import tier_for
            if tier_for(prof) != "ACTIVE":
                continue
        elif scope == "all-clone":
            if rejected:
                continue
        elif scope == "listed":
            pass  # filtered below
        else:
            raise ValueError(f"Unbekannter scope: {scope}")
        out.append(vid)
    if voice_id:
        if voice_id in out:
            return [voice_id]
        # Allow explicit listing even if not in current scope.
        if voice_id in reg._profiles:
            return [voice_id]
        print(_red(f"FEHLER: voice_id '{voice_id}' nicht im Registry."))
        sys.exit(2)
    return sorted(set(out))


# ---------------------------------------------------------------------------
# Manifest bootstrap (for legacy WAVs that don't yet have a .wav.json)
# ---------------------------------------------------------------------------
def _try_bootstrap_manifest(src_wav: Path, voice_id: str) -> tuple[bool, str]:
    """If a sidecar manifest is missing but the voice's recipe in
    voice_generation_recipes.json uses one of the canonical default ref
    texts, write the manifest sidecar next to the source WAV and return
    (True, "CREATED_MANIFEST"). Otherwise (False, reason).
    """
    from app.tts.reference_bundle import (
        _load_default_ref_texts, create_bundle,
    )
    recipes_p = ROOT / "project" / "voices" / "voice_generation_recipes.json"
    if not recipes_p.exists():
        return False, "voice_generation_recipes.json fehlt"
    data = json.loads(recipes_p.read_text(encoding="utf-8"))
    recipe = None
    for r in data.get("recipes", []):
        if r.get("voice_id") == voice_id:
            recipe = r; break
    if recipe is None:
        return False, f"Kein Recipe für {voice_id} in voice_generation_recipes.json"
    ref_text = recipe.get("reference_text")
    if not ref_text:
        # Kanonischen Default-Text anhand Sprache
        lang = recipe.get("language") or ("German" if voice_id.startswith("de_") else "English")
        en, de = _load_default_ref_texts()
        ref_text = de if lang == "German" else en
    language = recipe.get("language") or ("German" if voice_id.startswith("de_") else "English")
    seed = recipe.get("seed")
    bundle = create_bundle(
        voice_id=voice_id, wav_path=src_wav, ref_text=ref_text,
        language=language, seed=seed,
        description=f"manifest bootstrapped by import_voice_bundles.py for {voice_id}",
    )
    ok, summary, _ = bundle.validate()
    if not ok:
        return False, f"Konnte kein valides Manifest bauen:\n{summary}"
    write_bundle_atomically(bundle)
    return True, "Manifest erzeugt (canonical recipe)"


# ---------------------------------------------------------------------------
# Copy + verify
# ---------------------------------------------------------------------------
def _atomic_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".tmp_" + str(int(time.time() * 1000)))
    shutil.copy2(src, tmp)
    shutil.move(str(tmp), str(dst))


def import_one(voice_id: str, source_dir: Path, *,
               dry_run: bool, force: bool,
               bootstrap_missing_manifest: bool
               ) -> tuple[bool, str, dict]:
    src_wav = source_dir / f"{voice_id}.wav"
    src_manifest = manifest_path_for(src_wav)

    detail: dict = {"voice_id": voice_id, "source_wav": str(src_wav),
                    "source_manifest": str(src_manifest)}

    if not src_wav.exists():
        return False, f"QUELLE-WAV FEHLT: {src_wav}", detail
    if not src_manifest.exists():
        if bootstrap_missing_manifest:
            ok, msg = _try_bootstrap_manifest(src_wav, voice_id)
            if not ok:
                return False, f"MANIFEST FEHLT: {msg}", detail
            # Re-check
            if not src_manifest.exists():
                return False, "MANIFEST FEHLT (Bootstrap hat keine Datei erzeugt)", detail
        else:
            return False, f"MANIFEST FEHLT: {src_manifest}", detail

    bundle = load_bundle(src_wav, voice_id=voice_id)
    if bundle is None:
        return False, f"MANIFEST UNLESBAAR: {src_manifest}", detail
    ok, summary, vdetail = bundle.validate()
    if not ok:
        return False, f"VALIDIERUNG FEHLGESCHLAGEN:\n{summary}", detail
    detail.update(vdetail)

    dst_wav = bundled_bundle_path(voice_id)
    dst_manifest = manifest_path_for(dst_wav)

    action = "COPY  "
    if dst_wav.exists():
        existing_sha = sha256_file(dst_wav)
        if existing_sha.lower() == bundle.audio_sha256.lower():
            # Manifest ggf. nachziehen, falls es fehlt.
            manifest_uptodate = False
            if dst_manifest.exists():
                exist_b = load_bundle(dst_wav, voice_id=voice_id)
                if exist_b is not None and \
                   exist_b.audio_sha256.lower() == bundle.audio_sha256.lower():
                    manifest_uptodate = True
            if manifest_uptodate:
                return True, f"UNVERÄNDERT (SHA {bundle.audio_sha256[:12]}… bereits im Bundle)", detail
            action = "SYNC-M"     # manifest nachziehen
        elif force:
            action = "FORCE "
        else:
            return False, (
                f"KONFLIKT: {dst_wav} existiert mit abweichendem SHA "
                f"(existing={existing_sha[:12]}…, new={bundle.audio_sha256[:12]}…). "
                "Abgebrochen – nutze --force zum expliziten Überschreiben."), detail

    if dry_run:
        return True, f"[DRY-RUN] {action} dur={vdetail.get('duration_s','?')}s sha={bundle.audio_sha256[:12]}…", detail

    # Bitgenaue Kopie
    _atomic_copy(src_wav, dst_wav)
    _atomic_copy(src_manifest, dst_manifest)

    # Post-copy verify: SHA256 der Zieldatei MUSS identisch sein.
    post_sha = sha256_file(dst_wav)
    if post_sha.lower() != bundle.audio_sha256.lower():
        try:
            dst_wav.unlink()
            dst_manifest.unlink()
        except Exception:                                   # noqa: BLE001
            pass
        return False, (f"POST-COPY-VERIFY FEHLGESCHLAGEN: "
                       f"source-SHA {bundle.audio_sha256[:12]}… ≠ "
                       f"dest-SHA {post_sha[:12]}…"), detail
    post_bundle = load_bundle(dst_wav, voice_id=voice_id)
    if post_bundle is None:
        return False, f"POST-COPY: Manifest unlesbar ({dst_manifest})", detail
    ok2, sum2, _ = post_bundle.validate()
    if not ok2:
        return False, f"POST-COPY Validierung fehlgeschlagen:\n{sum2}", detail

    return True, f"{action} dur={vdetail.get('duration_s','?')}s sha={bundle.audio_sha256[:12]}…", detail


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--from-cache", action="store_true",
                     help="Aus project/cache/voice_refs/ importieren (Standard-Fall).")
    src.add_argument("--source", default=None,
                     help="Alternativer Quellordner (z.B. ein Backup).")
    ap.add_argument("--all", action="store_true",
                    help="Alle Clone-Stimmen (ACTIVE + BACKUPS + UNASSESSED) "
                         "importieren. Standard: nur ACTIVE Production-Stimmen.")
    ap.add_argument("--scope", choices=("production", "all-clone"),
                    default="production",
                    help="Welche Stimmen importiert werden sollen (default: production).")
    ap.add_argument("--voice-id", default=None,
                    help="Nur EINE bestimmte Voice-ID importieren.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Nur anzeigen, keine Dateien schreiben.")
    ap.add_argument("--force", action="store_true",
                    help="Bestehende Bundles auch bei SHA-Änderung überschreiben.")
    ap.add_argument("--bootstrap-missing-manifest", action="store_true",
                    help="Fehlt das .wav.json-Sidecar, versuche es aus "
                         "voice_generation_recipes.json zu erzeugen "
                         "(kanonische Referenztexte).")
    ap.add_argument("--json-report", default=None,
                    help="Schreibe detaillierten JSON-Report in diese Datei.")
    args = ap.parse_args()

    if args.all:
        args.scope = "all-clone"

    source_dir: Path
    if args.source:
        source_dir = Path(args.source)
        if not source_dir.is_absolute():
            source_dir = (Path.cwd() / source_dir).resolve()
    else:
        source_dir = paths.VOICE_REFS_DIR

    print(f"Quelle:        {source_dir}")
    print(f"Ziel (Bundles): {paths.BUNDLED_REF_DIR}")
    print(f"Scope:         {args.scope}" + (f" + --voice-id {args.voice_id}" if args.voice_id else ""))
    print(f"Dry-Run:       {args.dry_run}")
    print(f"Force:         {args.force}")
    print()

    if not source_dir.is_dir():
        print(_red(f"FEHLER: Quellordner existiert nicht: {source_dir}"))
        return 2

    targets = _target_voices(voice_id=args.voice_id, scope=args.scope)
    if args.voice_id and not targets:
        return 2
    if not targets:
        print(_yellow("Keine Zielstimmen gefunden."))
        return 0

    print(f"Importiere {len(targets)} Stimmen …\n")
    ok_n = 0
    fail_n = 0
    results: list[dict] = []
    for vid in targets:
        ok, msg, det = import_one(
            vid, source_dir, dry_run=args.dry_run, force=args.force,
            bootstrap_missing_manifest=args.bootstrap_missing_manifest)
        det["ok"] = ok
        det["message"] = msg
        results.append(det)
        if ok:
            print(_green("  [OK]  ") + f"{vid}: {msg}")
            ok_n += 1
        else:
            print(_red("  [!!]  ") + f"{vid}: {msg}")
            fail_n += 1

    print()
    print(f"Ergebnis: {ok_n} ok, {fail_n} fehlgeschlagen "
          f"(von {len(targets)} Stimmen).")
    if args.json_report:
        rp = Path(args.json_report)
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(json.dumps({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "source_dir": str(source_dir),
            "bundle_dir": str(paths.BUNDLED_REF_DIR),
            "dry_run": args.dry_run,
            "force": args.force,
            "results": results,
            "summary": {"total": len(targets), "ok": ok_n, "fail": fail_n},
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"JSON-Report geschrieben: {rp}")

    if fail_n:
        print()
        print(_yellow("Hinweis bei fehlgeschlagenen Stimmen:"))
        print("  * Wenn die Quelle-WAV fehlt, wurde diese Stimme auf diesem")
        print("    Host noch nicht materialisiert – führe auf dem GPU-Host aus:")
        print("      python project/tools/materialize_references.py")
        print("    und wiederhole den Import.")
        print("  * Wenn das Manifest fehlt, starte mit")
        print("    --bootstrap-missing-manifest (nur bei kanonischen Rezepten).")
        return 1
    print()
    print(_green("Alle Zielstimmen erfolgreich importiert. Nächste Schritte:"))
    print("  python project/tools/validate_reference_bundles.py")
    print("  git add project/app/voices/bundles/")
    print("  git commit -m \"feat(voices): import production reference bundles\"")
    print("  git push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
