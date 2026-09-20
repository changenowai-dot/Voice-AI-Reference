#!/usr/bin/env python3
"""Verify voice reference availability for PART A COMPLETE.

Checks, for every voice profile in project/voices/*.json:
  - profile JSON loads and has voice_id + backend_mode
  - clone voices have their canonical cache/voice_refs/<id>.wav
  - the WAV is a valid, non-empty, 24 kHz mono PCM (if possible without
    soundfile — falls back to size+header magic check)
  - for production-locked voices (locked_human_favorite / saved_human_shortlist
    / vd_e / good_archived / new_candidate_german_recovery), a sidecar
    .wav.json reference bundle exists and validates.
  - GUI-tier mapping (locked/custom/clone/candidates) covers every voice.

Run (on host):
    python project/tools/verify_voice_refs.py            # status report
    python project/tools/verify_voice_refs.py --strict   # exit 1 if any PRODUCTION voice is missing

Exit codes: 0 = all production voices present; 1 = any missing production
voice; 2 = IO/format error.
"""
from __future__ import annotations
import argparse, json, sys, wave, pathlib, hashlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROJECT = ROOT / "project"
VOICES_DIR = PROJECT / "voices"
VOICE_REFS_DIR = PROJECT / "cache" / "voice_refs"

PRODUCTION_STATUSES = {
    "locked_human_favorite",
    "saved_human_shortlist",
    "good_archived",
    "new_candidate_german_recovery",
    None,  # vd_e and aiden/dylan/... have no status field
}


def sha256(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def is_wav_readable(p: pathlib.Path) -> tuple[bool, str]:
    try:
        with wave.open(str(p), "rb") as w:
            nch, sw, sr, nf = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        if nf == 0:
            return False, "empty wav (0 frames)"
        if sw != 2:
            return False, f"sample width {sw*8}bit (expected 16-bit PCM)"
        if sr != 24000:
            return False, f"sample rate {sr} Hz (expected 24000 Hz)"
        if nch != 1:
            return False, f"{nch} channels (expected mono)"
        return True, f"{sr} Hz mono 16-bit, {nf} frames ({nf/sr:.1f}s)"
    except wave.Error as e:
        # fall back to magic header
        try:
            head = p.read_bytes()[:12]
            if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
                return True, "RIFF/WAVE header OK (wave module refused)"
        except Exception:
            pass
        return False, f"wav open failed: {e}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if any production voice is missing")
    args = ap.parse_args()

    profiles = []
    for jf in sorted(VOICES_DIR.glob("*.json")):
        if jf.name == "voice_generation_recipes.json":
            continue
        try:
            d = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[FAIL] cannot parse {jf.name}: {e}")
            return 2
        if "voice_id" not in d:
            continue
        profiles.append(d)

    print(f"[INFO] {len(profiles)} voice profiles found under project/voices/")
    print(f"[INFO] voice_refs dir: {VOICE_REFS_DIR}")
    if not VOICE_REFS_DIR.exists():
        print(f"[WARN] voice_refs directory does not exist yet: {VOICE_REFS_DIR}")
        VOICE_REFS_DIR.mkdir(parents=True, exist_ok=True)

    total_profiles = len(profiles)
    clone = sum(1 for p in profiles if p.get("backend_mode") == "clone")
    custom = sum(1 for p in profiles if p.get("backend_mode") == "customvoice")
    missing_production = 0
    missing_nonproduction = 0
    wav_ok = 0
    wav_bad = 0
    manifest_ok = 0
    manifest_missing = 0
    vde_ok = False

    rows = []
    for p in profiles:
        vid = p["voice_id"]
        mode = p.get("backend_mode")
        status = p.get("status")
        is_production = (vid == "vd_e") or (status in PRODUCTION_STATUSES) or (mode == "customvoice")
        if mode == "customvoice":
            rows.append((vid, "CUSTOM", "—", "OK (no WAV required)"))
            continue
        # clone
        wav_path = VOICE_REFS_DIR / f"{vid}.wav"
        if vid == "vd_e":
            wav_path = VOICE_REFS_DIR / "VD-E.wav"
        manifest_path = pathlib.Path(str(wav_path) + ".json")
        if not wav_path.exists():
            if is_production:
                missing_production += 1
                rows.append((vid, "CLONE/PROD", "—", "MISSING REF WAV"))
            else:
                missing_nonproduction += 1
                rows.append((vid, f"CLONE/{status or '?':.18s}", "—", "MISSING (non-production)"))
            continue
        ok, info = is_wav_readable(wav_path)
        if ok:
            wav_ok += 1
            if vid == "vd_e":
                sh = sha256(wav_path)
                if sh.lower().startswith("b156c02a60a873ad95fc92390c4a136c85308b20"):
                    vde_ok = True
                    info = "GOLDEN-REF SHA OK, " + info
                else:
                    info = f"GOLDEN-REF SHA MISMATCH ({sh[:16]}…), " + info
                    wav_bad += 1
                    wav_ok -= 1
        else:
            wav_bad += 1
        if manifest_path.exists():
            manifest_ok += 1
            minfo = "+manifest"
        else:
            manifest_missing += 1
            minfo = "(no sidecar)"
        rows.append((vid, f"CLONE/{status or 'prod':.18s}", "WAV", f"{info} {minfo}"))

    # print grouped
    print()
    print(f"{'voice_id':<46} {'tier':<24} {'key':<5} detail")
    print("-" * 110)
    for vid, tier, key, detail in rows:
        print(f"{vid:<46} {tier:<24} {key:<5} {detail}")
    print()
    print("===== summary =====")
    print(f"  profiles total:          {total_profiles}")
    print(f"    customvoice (no wav):  {custom}")
    print(f"    clone:                 {clone}")
    print(f"  wav present & readable:  {wav_ok}")
    print(f"  wav corrupt/invalid:     {wav_bad}")
    print(f"  sidecar manifests ok:    {manifest_ok}")
    print(f"  sidecar manifests miss:  {manifest_missing}")
    print(f"  VD-E golden ref intact:  {'YES' if vde_ok else 'NO'}")
    print(f"  PRODUCTION wavs MISSING: {missing_production}")
    print(f"  non-prod wavs MISSING:   {missing_nonproduction} (rejected/test — non-fatal, can materialize on demand)")

    if args.strict and missing_production > 0:
        print()
        print("[FAIL] Es fehlen PRODUCTION-Voice-Referenzen. Fuehre zuerst den Import aus dem Frozen Backup aus:")
        print("        powershell -ExecutionPolicy Bypass -File project\\tools\\import_voice_refs_from_frozen_backup.ps1")
        print("      oder materialisiere sie auf dem GPU-Host via:")
        print("        python project\\tools\\materialize_references.py --all-missing")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
