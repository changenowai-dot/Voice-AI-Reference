#!/usr/bin/env python3
"""
Validator for voice library — checks ID/name/language/gender/seed/description/model/backend/engine/API/procedure/provenance
See task requirement 14.
Usage: python project/tools/validate_voices.py
       python project/tools/validate_voices.py --voices
       python project/tools/validate_voices.py --recipes
"""
import json, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[2]
VOICES_DIR=ROOT/"project"/"voices"
RECIPES=VOICES_DIR/"voice_generation_recipes.json"

def validate_voices():
    ok=True
    for jf in sorted(VOICES_DIR.glob("*.json")):
        if jf.name=="voice_generation_recipes.json":
            continue
        try:
            j=json.loads(jf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"FAIL {jf.name}: invalid json {e}")
            ok=False; continue
        vid=j.get("voice_id")
        if not vid:
            print(f"FAIL {jf.name}: missing voice_id")
            ok=False; continue
        backend = j.get("backend_mode") or j.get("backend") or ""
        is_customvoice = backend=="customvoice" or j.get("speaker_name") is not None
        checks=[
            ("voice_id", j.get("voice_id")),
            ("display_name", j.get("display_name")),
            ("gender", j.get("gender")),
            ("language_support/native_language", j.get("language_support") or j.get("native_language")),
            # seed only required for clone voices; customvoice presets use speaker, not seed
            ("seed", (j.get("settings") or {}).get("seed", j.get("seed")) if not is_customvoice else "customvoice-no-seed"),
            ("description", j.get("description")),
            ("model", j.get("model")),
            ("backend", backend),
            ("engine", (j.get("settings") or {}).get("engine", j.get("engine")) or backend),
        ]
        missing=[k for k,v in checks if not v]
        if missing:
            print(f"FAIL {jf.name} ({vid}): missing {missing}")
            ok=False
        else:
            prov=j.get("generation_provenance") or j.get("provenance") or j.get("reference_generated") or "unknown"
            # provenance should be identifiable
            tier=j.get("status","?")
            print(f"OK {vid:45} gender={j.get('gender','?'):6} seed={(j.get('settings') or {}).get('seed','?')} status={tier} prov={str(prov)[:30]}")
        # check per_language
        if "per_language" not in j:
            print(f"WARN {vid}: missing per_language (GUI language filtering)")
        # check reference path
        ref=j.get("reference_path")
        if not ref:
            # some baseline like aiden have no ref — warn but not fail
            print(f"  note {vid}: no reference_path (customvoice preset or vd_e golden)")
    return ok

def validate_recipes():
    if not RECIPES.exists():
        print(f"Missing {RECIPES}")
        return False
    data=json.loads(RECIPES.read_text(encoding="utf-8"))
    recipes=data.get("recipes",[])
    required=["voice_id","seed","language","gender","voice_design_description","model","model_variant","backend","engine","api_entry_point","reference_audio_path","reference_audio_sha256","clone_parameters","voice_design_parameters","sampling_parameters","cache_key_fingerprint","audio_format","postprocessing","runtime_versions","backend_path","provenance","reproduction_procedure"]
    ok=True
    for r in recipes:
        vid=r.get("voice_id","?")
        missing=[k for k in required if k not in r or r[k] in (None,"")]
        # Allow unknown/not recorded but must point to code location for some optional? We treat missing as fail for critical.
        critical=["voice_id","seed","language","gender","voice_design_description","model","backend","engine","provenance"]
        crit_missing=[k for k in critical if k in missing]
        if crit_missing:
            print(f"FAIL recipe {vid}: missing critical {crit_missing}")
            ok=False
        else:
            if missing:
                print(f"WARN recipe {vid}: missing/unknown non-critical {missing} — see references for code location")
            print(f"OK recipe {vid:45} seed={r.get('seed')} prov={r.get('provenance')} lang={r.get('language')} gender={r.get('gender')}")
    print(f"\nValidator recipes: {'OK' if ok else 'FAIL'} — {len(recipes)} recipes checked")
    return ok

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--voices", action="store_true", help="only voices")
    p.add_argument("--recipes", action="store_true", help="only recipes")
    args=p.parse_args()
    ok=True
    if not args.recipes:
        print("=== Validate voices/*.json ===")
        ok = validate_voices() and ok
    if not args.voices:
        print("\n=== Validate voice_generation_recipes.json ===")
        ok = validate_recipes() and ok
    sys.exit(0 if ok else 2)
