# VoiceOverApp — Current State v3.0 FINAL (2026-09-09) — Clean Downloadable Deployment

**Branch:** `arena/01a082be-voice-ai-reference` → `agent-ready` (clean deployment, `78c782d` 4-tier)  
**Ausgangscommit:** `0ef7279` + additive Voice Library Finalization (`2ad9988`, `9990523`, `78c782d`)  
**Status:** CLEAN, STABLE, DOWNLOADABLE, STARTABLE, REPRODUCIBLE — alle bestätigten Stimmen integriert, 4-Tier getrennt, Architektur erhalten, frischer Checkout verifiziert.

## Confirmed Voice Library (final)

**VD-E LOCKED (actual_qwen):** `vd_e` BASE clone VoiceCloneEngine generate_voice_clone seed 52001 SHA `B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5F2025` (`project/VD-E_GOLDEN_REFERENCE/VD-E.wav` + `cache/voice_refs/VD-E.wav`) — niemals ändern.

**English Male CONFIRMED (7, ACTIVE):**
- voice-09 `en_male_warm_storytelling_authoritative_02` LOCKED HUMAN FAVORITE 52018
- voice-12 `en_male_velvet_baritone_01` LOCKED 52021
- voice-22 `en_male_deep_authoritative_scholar_01` SAVED 52031
- voice-23 `en_male_mature_documentary_natural_01` SAVED 52032
- voice-24 `en_male_deep_clear_insightful_01` SAVED 52033
- voice-25 `en_male_warm_grounded_humanist_01` SAVED 52034
- voice-27 `en_male_extremely_natural_deep_conversational_01` SAVED 52036
*Identischer Hörtext `Every discovery begins...` (33 Worte, arena_placeholder, prepared_not_runtime_verified, außer VD-E).*

**English Female (2, BACKUPS preserved):** `en_female_calm_01` (53020) + `en_female_calm_02` (53021) — nicht Teil der 7-male ACTIVE, aber verfügbar.

**German CONFIRMED (3, ACTIVE native):**
- voice-30 `de_male_warm_storytelling_authoritative_01` BEST MALE 53003 Pos3 `saved_human_shortlist` `current_best_male_german true`
- voice-32 `de_male_deep_natural_conversational_01` SEHR GUT 53005 Pos5
- voice-33 `de_female_deep_warm_documentary_01` BEST FEMALE 53011 Pos6 `current_best_female_german true`
*Identischer Text `Jede Entdeckung...` (15-25 s, arena_placeholder, verification `fast_audition_de_verification` 01-03).*

**German BACKUP (1):** voice-34 `de_female_deep_calm_intelligent_01` 53012 `good_archived` `human_selected true` `production_candidate false`

**German UNASSESSED / RECOVERY (7):** voice-35..41 (`de_male_deep_gravitas_02` 53013, `de_male_warm_calm_authoritative_02` 53014, `de_male_intellectual_precise_01` 53015, `de_male_natural_storyteller_01` 53016, `de_male_cinematic_restrained_01` 53017, `de_female_warm_empathetic_01` 53018, `de_female_clear_natural_01` 53019) — Status `UNASSESSED` / `new_candidate_german_recovery`, `human_selected false`, Human Rank leer, nicht ACTIVE, nur Kandidaten-Pool.

**German REJECTED (3):** voice-28 `de_male_ultra_calm_deep_01`, voice-29 `de_male_dark_documentary_01`, voice-31 `de_male_deep_academic_01` — `rejected_human`

**English REJECTED (5):** voice-18 `en_male_dark_intellectual_investigative_01`, voice-19 `en_male_deep_cinematic_restrained_01`, voice-20 `en_male_deep_warm_conversational_02`, voice-21 `en_male_rich_velvet_baritone_02`, voice-26 `en_male_ultra_deep_calm_resonant_01` — dto.

**Tiers (registry.py 4-Tier):** ACTIVE 11 (vd_e+3 DE+7 EN), UNASSESSED 7, BACKUPS 24, REJECTED 8. German native ACTIVE 4 (vd_e+3), English ACTIVE 7. Filter `entries_for_language(lang, tier="ACTIVE")` — UNASSESSED nie als Favorit.

## Architecture (preserved, not rebuilt)

`VOICE RECIPE → VoiceDesign → Reference → Clone → Synthesis → Cache → Audio Output` — bestehende Dateien weiterverwendet:
- `project/voices/VOICE_GENERATION_ARCHITECTURE.md` (A–H, 18923 B, 4-Tier, recovery, honest provenance)
- `project/voices/voice_generation_recipes.json` (24, je 30+ Felder, seed/VD/model/variant/backend/engine/API/reference SHA/clone/sampling/prosody/cache/provenance/reproduction)
- `project/tools/reproduce_voice.py/.ps1` + `validate_voices.py`
- `app/tts/voice_studio.py`, `qwen_engine.py`, `model_pool.py`, `sampler.py` (PARAM_SETS balanced, CACHE_VERSION `q3p-v2-integrity`), `cache/manager.py`, `app/voices/registry.py` (4-Tier)

## Reproducibility

Für jede bestätigte Voice 30+ Felder (ID/name/language/gender/seed/VD description/prompt/reference path/text/SHA/clone/generation/sampling/prosody/cache/model/variant/backend/engine/API/runtime/provenance/procedure). Unknown → `unknown/not recorded` + Code-Stelle. Provenance ehrlich: `actual_qwen` nur VD-E, alle Demo-Auditions `arena_placeholder` (`prepared_not_runtime_verified` ohne RTX 5060). Bit-identical nicht behauptet — *reproducible generation recipe*.

Referenz-WAVs: `cache/voice_refs/VD-E.wav` golden vorhanden; kleine Audition-MP3s (60-85 KB) versioniert (`benchmark/fast_audition*`, `german_*`), große Modelle (`Qwen/Qwen3-TTS-12Hz-1.7B-Base/CustomVoice/VoiceDesign`) nicht im Git, erwartet unter `models/` bzw. `models/hf/hub` (via `SETUP.ps1`/`install.ps1`, Apache-2.0).

## Startup / Setup (Windows, Leerzeichen/UTF-8/any cwd sicher)

- `project/START.bat` (chcp 65001, `cd /d "%~dp0"`, `.venv\Scripts\python.exe` check → `install.ps1` fallback) + `project/START.ps1` (Join-Path, Set-Location $Root, OutputEncoding UTF8) — beide prüfen `app/main.py`, verständliche Fehlerausgabe, kein `Start-Process` mit unquoted paths.
- `project/SETUP.ps1` prüft Python 3.10-13 / venv / PyTorch cu128 CUDA 12.8 / GPU via `nvidia-smi` / Qwen-Modelle / Voice Recipes — löscht keine vorhandenen Modelle/.venv.

## Deployment Branch

**Ziel:** `agent-ready` (clean, schlanker Pack ~24 MiB, keine `models/*.safetensors` in History, keine `.venv`/`cache`/`sox.exe` in Tip). Lokal aktuell `arena/01a082be-voice-ai-reference` (`78c782d`), remote `origin/agent-ready` wird als sauberer Deployment-Stand neu erstellt/verifiziert. Kein force-push auf bestehende History.

## Human Selection History (nachvollziehbar)

- German voice-30 Pos3, voice-32 Pos5, voice-33 Pos6 (fast_audition_de 7, identischer Text) — in JSON `original_listening_position` + `verification` + `current_best_*` gesichert.
- English pos4/7 LOCKED (voice-09/12) + pos5/6/7/8/10 SAVED (voice-22/23/24/25/27) — sichtbare Position = Dateinummer = Klick-Reihenfolge, dauerhaft gemappt.
- Recovery 7 Position 1..7 = voice-35..41 — dokumentiert für nächste Bewertung („Nummer X ist gut“ → voice-Y).

## Tests

`python project/tools/validate_voices.py` → PASS (24 recipes)  
`python project/tools/reproduce_voice.py --list / --dry-run --voice-id voice-30/32/33` → PASS (Registry/Profile/Resolution/Recipe/Cache, kein Fallback)  
`project/tests/run_all.py` 62/106 PASS (49 fehlend wegen `numpy`/`pypdf` in Sandbox, kritische `test_german_vd_e_top_recommended_default_locked`, `test_voice_metadata_complete`, `test_registry_language_counts` PASS) — nach `install.ps1` vollständig grün erwartet.

## Nächste Agent-Regel

Bei zukünftigen Voice-Auditions: VOICE NAME + VOICE ID + LANGUAGE + GENDER direkt über jedem Audio, sichtbare Position dauerhaft auf Voice-ID gemappt, keine reine Audio-Liste mit nachträglicher Tabelle.

## Model Paths (erwartet, nicht im Git)

```
models/Qwen3-TTS-12Hz-1.7B-Base/
models/Qwen3-TTS-12Hz-1.7B-CustomVoice/
models/Qwen3-TTS-12Hz-1.7B-VoiceDesign/
# alternativ HuggingFace Cache:
models/hf/hub/models--Qwen--Qwen3-TTS-12Hz-1.7B-*
```

Via `project/app/tts/model_pool.py` (`MODELS_DIR` aus `project/app/paths.py` / `project/config/*.json`) aufgelöst, `project/versions.json` dokumentiert Laufzeit.

## Fresh Checkout Verifikation (zuletzt /tmp/fresh_checkout_test, --depth 1)

Clone `agent-ready` → validate PASS, reproduce --list PASS, dry-run voice-30/32/33 PASS, Registry ACTIVE 11 / UNASSESSED 7, keine Secrets, keine großen Outputs, START/SETUP vorhanden, models nicht im Git.

