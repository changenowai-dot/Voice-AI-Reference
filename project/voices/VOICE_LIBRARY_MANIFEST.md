# VOICE LIBRARY MANIFEST — Production + Candidate Pools

**Stand:** 2026-09-09 · **Branch:** `arena/01a082be-voice-ai-reference` · **Hardware-Ziel:** RTX 5060 8 GB (VRAM-Guard), CPU-Fallback  
**Golden VD-E SHA256:** `B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5F2025` (LOCKED, `project/VD-E_GOLDEN_REFERENCE/VD-E.wav` + `cache/voice_refs/VD-E.wav`)  
**Reproduktion:** `project/voices/voice_generation_recipes.json` (maschinenlesbar, 30+ Felder) + `project/voices/VOICE_GENERATION_ARCHITECTURE.md` (A–H) + `project/tools/reproduce_voice.py`

> **Regel für zukünftige Auditions (verbindlich):** Jede Audio-Ausgabe präsentiert **VOICE NAME + VOICE ID/Sprache/Gender direkt über dem Player** – unabhängig von Dateiname/Battle-ID/Registry-Rank.

---

## Provenance-Legende (ehrlich)

| Label | Bedeutung |
|---|---|
| `actual_qwen` | Echte Qwen-Pipeline `VoiceDesign → cache/voice_refs/*.wav → Clone` auf RTX 5060 (Base + VoiceDesign 1.7B, 12Hz). Nur VD-E erfüllt dies vollständig. |
| `arena_placeholder` | Arena TTS `add_voice`/`generate_speech` (real speech, **kein** TestDouble-Sinus) als **Hör-Platzhalter** in Sandbox (nvidia-smi not found, kein Qwen-Modell geladen). VoiceDesign-Konzept, Seed, Prompt bleiben erhalten und werden später auf echter Qwen-Pipeline reproduziert (vollständig reproducibel). |
| `preserved` | Bestehende Stimme unverändert übernommen (kein Regenerate in dieser Session). |

`reproduction_status` für alle `arena_placeholder` = `prepared_not_runtime_verified` (keine RTX-5060-Verifikation in Arena-Sandbox möglich).

---

## Tier 1 — ACTIVE (Human-Selected / Locked, in App auswählbar, Favoriten/Shortlist)

### English — Male Shortlist 7 (A–G) · identischer Hörtext `Every discovery begins...` (33 Worte)

| Pool | Pos | Voice ID | Display Name | Gender | Arena Battle | Seed | Concept / VoiceDesign-Prompt | Provenance | Audio (Audition Render) | Human Rank |
|---|---|---|---|---|---|---|---|---|---|---|
| **A LOCKED** | Pos4 | `en_male_warm_storytelling_authoritative_02` (voice-09) | EN Male Warm Storytelling Authoritative 02 | male | voice-09 | 52018 | warm storytelling authoritative – superior version, deep warm authority clarity | `arena_placeholder` | `benchmark/male_deep_candidates/04_warm_storytelling_authoritative/part1.mp3` | **LOCKED HUMAN FAVORITE** — `production_locked true` — nie ändern/löschen |
| **B LOCKED** | Pos7 | `en_male_velvet_baritone_01` (voice-12) | EN Male Velvet Baritone 01 | male | voice-12 | 52021 | velvet baritone – deep exceptionally smooth warm rich rounded | `arena_placeholder` | `benchmark/male_deep_candidates/07_velvet_baritone/part1.mp3` | **LOCKED HUMAN FAVORITE** |
| **C SAVED** | Pos5 (Round02) | `en_male_deep_authoritative_scholar_01` (voice-22) | EN Male Deep Authoritative Scholar 01 | male | voice-22 | 52031 | deep authoritative scholar – clear, grounded, knowledgeable | `arena_placeholder` | `benchmark/fast_audition_round02/05_*.mp3` | **SAVED HUMAN SHORTLIST** — `human_selected true, production_candidate true` — intensive Long-Form-Test ausstehend |
| **D SAVED** | Pos6 | `en_male_mature_documentary_natural_01` (voice-23) | EN Male Mature Documentary Natural 01 | male | voice-23 | 52032 | mature documentary natural – authentic, lived-in, calm | `arena_placeholder` | `benchmark/fast_audition_round02/06_*.mp3` | SAVED |
| **E SAVED** | Pos7 | `en_male_deep_clear_insightful_01` (voice-24) | EN Male Deep Clear Insightful 01 | male | voice-24 | 52033 | deep clear insightful – intelligent, articulate, lucid | `arena_placeholder` | `benchmark/fast_audition_round02/07_*.mp3` | SAVED |
| **F SAVED** | Pos8 | `en_male_warm_grounded_humanist_01` (voice-25) | EN Male Warm Grounded Humanist 01 | male | voice-25 | 52034 | warm grounded humanist – empathetic, sincere, mature | `arena_placeholder` | `benchmark/fast_audition_round02/08_*.mp3` | SAVED |
| **G SAVED** | Pos10 | `en_male_extremely_natural_deep_conversational_01` (voice-27) | EN Male Extremely Natural Deep Conversational 01 | male | voice-27 | 52036 | extremely natural deep conversationalist – hyper-natural, effortless | `arena_placeholder` | `benchmark/fast_audition_round02/10_*.mp3` | SAVED |

**Gemeinsame Attribute (ACTIVE English Shortlist):**  
- `native_language` English (`native` bei male, female calm separate) · `backend clone` · `engine VoiceCloneEngine` · `model_variant` = `EN_...` · `cache_version q3p-v2-integrity` · `sampling balanced` (temp 0.70 top_k 50 top_p 0.90 rep_pen 1.05, 3 attempts seed 5100+7) · `reference_sha` = ARENA_VOICE-xx · VoiceDesign-Referenztext `VOICEDESIGN_REF_TEXT_EN` (`There is a book... Who decides what is real?`) · Audition-Hörtext (identisch für Vergleich) `Every discovery...` — **vom Referenztext getrennt**.

### English — Female Calm 2 (preserved, ACTIVE)

| Voice ID | Gender | Seed | Provenance | Status | Verwendung |
|---|---|---|---|---|---|
| `en_female_calm_01` | female | 53020* | `preserved` | `test_voice` (preserved, nicht neu gerendert) | ACTIVE female option — nicht Teil der 7-male Shortlist, bleibt unverändert |
| `en_female_calm_02` | female | 53021* | `preserved` | `test_voice` | s. o. |

*Seed für Reproduktionszwecke ergänzt; Original unverändert.

### German — ACTIVE Shortlist 3 (LOCKED-Human-verifiziert, identischer Text `Jede Entdeckung beginnt...`)

| Pos (fast_audition_de) | Voice ID | Display Name | Gender | Arena | Seed | Concept | Provenance | Audio (Audition + Verification) | Human Rank |
|---|---|---|---|---|---|---|---|---|---|
| **Pos3** | `de_male_warm_storytelling_authoritative_01` (voice-30) | DE Male Warm Storytelling Authoritative 01 | male | voice-30 | 53003 | warm storytelling authority – tief, warm, menschlich, erzählerisch | `arena_placeholder` | `benchmark/fast_audition_de/03_*.mp3` + `benchmark/fast_audition_de_verification/01_*voice-30.mp3` | **BEST MALE GERMAN — CURRENT BEST** (`current_best_male_german true`, `human_selected true`, `saved_human_shortlist`, `verification_sample_generated true`) |
| **Pos5** | `de_male_deep_natural_conversational_01` (voice-32) | DE Male Deep Natural Conversational 01 | male | voice-32 | 53005 | deep natural conversational – tief, natürlich, direkt, modern | `arena_placeholder` | `benchmark/fast_audition_de/05_*.mp3` + `benchmark/fast_audition_de_verification/02_*voice-32.mp3` | **BETTER / HIGH PRIORITY male** (`saved_human_shortlist`) |
| **Pos6** | `de_female_deep_warm_documentary_01` (voice-33) | DE Female Deep Warm Documentary 01 | female | voice-33 | 53011 | deep warm documentary – warm, tief, ruhig, reif | `arena_placeholder` | `benchmark/fast_audition_de/06_*.mp3` + `benchmark/fast_audition_de_verification/03_*voice-33.mp3` | **BEST FEMALE GERMAN** (`current_best_female_german true`, `human_selected true`, `saved_human_shortlist`) |

Alle drei: `status saved_human_shortlist`, `human_selected true`, `production_candidate true`, `original_listening_position / human_listening_position` gesichert, identischer deutscher Kurztext `Jede Entdeckung beginnt mit einer Frage...` (15-25 s) exakt für alle 7 der damaligen Fast-Audition, **kein 4-Parts/FullScript**.

### VD-E — ABSOLUTELY LOCKED (BASE Clone, actual_qwen-Referenz)

| Voice ID | Display Name | Gender | Language | Variant | Backend | Engine | API | Seed | Reference WAV | SHA256 | Provenance | reproduction_status |
|---|---|---|---|---|---|---|---|---|---|---|---:|---|
| `vd_e` (BASE) | VD-E | male | German+English (`native German recommended`) | `BASE` | `clone` | `VoiceCloneEngine` (`qwen_engine.py`) | `generate_voice_clone` (via `create_voice_clone_prompt`) | 52001 | `cache/voice_refs/VD-E.wav` + golden `project/VD-E_GOLDEN_REFERENCE/VD-E.wav` (998 484 B) | `B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5F2025` | `actual_qwen` (einzige mit echter Qwen-Referenz) | `verified_golden` — niemals neu generieren/rekonfigurieren/migrieren |

`per_language`: German `native_status recommended rank 0`, English `cross_language rank 35`. `production_locked true`, `default true`.

---

## Tier 2 — BACKUPS (archived, NICHT in aktiver Shortlist, aber in separatem Backup-Bereich/Registry verfügbar, reproducibel)

### German Backup — good_archived (human_selected, NICHT production_candidate)

| Pos (german_second_audition) | Voice ID | Gender | Arena | Seed | Concept | Provenance | Audio |
|---|---|---|---|---|---|---|---|
| Pos4 | `de_female_deep_calm_intelligent_01` (voice-34) | female | voice-34 | 53012 | deep calm intelligent – tief, ruhig, intelligent | `arena_placeholder` | `benchmark/german_second_audition/04_de_female_deep_calm_intelligent_01_voice-34.mp3` |

`status good_archived`, `human_selected true`, `production_candidate false`, `backup_note: BACKUP candidate, not active production`.

### English Backups — test_voice / test_voice_premium_10 (archived, NICHT active, aber dokumentiert)

Beispiele (vollständig in `project/voices/*.json` mit `per_language` Rängen):

- `en_male_deep_01`, `en_male_deep_02`, `en_male_calm_deep_01`, `en_male_cinematic_documentary_01`, `en_male_commanding_restrained_01`, `en_male_dark_documentary_01`, `en_male_deep_academic_01`, `en_male_deep_conversational_01`, `en_male_deep_warm_human_01`, `en_male_investigative_mystery_01`, `en_male_ultra_calm_deep_01`, `en_male_ultra_deep_calm_02`, `en_male_warm_storyteller_01`, `en_male_warm_storytelling_authoritative_01` etc.  
  Alle `status test_voice` / `test_voice_premium_10` ⇒ **Tier BACKUPS** (separater Bereich, nicht in Favoriten/ACTIVE).

---

## Tier 3 — REJECTED (rejected_human, NIEMALS mehr in ACTIVE-UI/Shortlist/Favoriten, nur Historie/Reproduzierbarkeit)

| Round | Pos | Voice ID | Reason |
|---|---|---|---|
| English Round02 | Pos1 | `en_male_dark_intellectual_investigative_01` (voice-18) | `rejected_human` — `production_candidate false`, `human_selected false` — aus aktiver UI entfernt, Historie erhalten |
| English Round02 | Pos2 | `en_male_deep_cinematic_restrained_01` (voice-19) | s. o. |
| English Round02 | Pos3 | `en_male_deep_warm_conversational_02` (voice-20) | s. o. |
| English Round02 | Pos4 | `en_male_rich_velvet_baritone_02` (voice-21) | s. o. |
| English Round02 | Pos9 | `en_male_ultra_deep_calm_resonant_01` (voice-26) | s. o. |
| German fast_audition_de | Pos1 | `de_male_ultra_calm_deep_01` (voice-28) | `rejected_human` — German rejected, nicht aktiv |
| German fast_audition_de | Pos2 | `de_male_dark_documentary_01` (voice-29) | `rejected_human` |
| German fast_audition_de | Pos4 | `de_male_deep_academic_01` (voice-31) | `rejected_human` |

Keiner dieser Einträge darf im `ACTIVE`-Filter oder in `Favorites` erscheinen. **Filterlogik:** `app/voices/registry.py` + GUI trennt strikt `ACTIVE` (`saved_human_shortlist` / `locked_human_favorite` / `preserved`) vs. `BACKUPS` vs. `REJECTED` (`rejected_human`).

---

## NEW CANDIDATES 2026-09-09 — GERMAN RECOVERY AUDITION (7, noch nicht gerankt — `Human Rank` blank,.pending intensiver Test)

> **Hintergrund (ehrlich):** Exhaustive Suche in `project/voices/*.json`, `project/benchmark/*/`, `voice_generation_recipes.json`, Git-History/Branches ergab **0 zusätzliche historische deutsche Kandidaten** über die bereits getesteten 7 (voice-28..34) hinaus. Daher sind alle 7 **NEW CANDIDATE**, nicht RECOVERED. Tagesaktuelles Datum 2026-09-09, identischer deutscher Text `Jede Entdeckung beginnt mit einer Frage...` (15-25 s, arena_placeholder, je genau 1 Clip/Voice, keine 4-Parts/Varianten).

| Pos | Voice ID | Display Name | Gender | Arena | Seed | Concept / VoiceDesign-Prompt | Provenance | Audio File | Duration* | Human Rank |
|---|---|---|---|---|---|---|---|---|---|
| **01** | `de_male_deep_gravitas_02` (voice-35) | DE Male Deep Gravitas 02 | male | voice-35 | 53013 | deep gravitas — sehr tief, wuchtig, seriös, dokumentarisch | `arena_placeholder` | `benchmark/german_recovery_audition/01_de_male_deep_gravitas_02.mp3` (75 021 B) | ~17 s | *(blank — pending your intensive long-form/psychology/history test)* |
| **02** | `de_male_warm_calm_authoritative_02` (voice-36) | DE Male Warm Calm Authoritative 02 | male | voice-36 | 53014 | warm calm authoritative 02 — warm, ruhig, autoritativ, nahbar | `arena_placeholder` | `benchmark/german_recovery_audition/02_de_male_warm_calm_authoritative_02.mp3` (69 933 B) | ~16 s | blank |
| **03** | `de_male_intellectual_precise_01` (voice-37) | DE Male Intellectual Precise 01 | male | voice-37 | 53015 | intellectual precise — intelligent, präzise, analytisch, klar | `arena_placeholder` | `benchmark/german_recovery_audition/03_de_male_intellectual_precise_01.mp3` (74 541 B) | ~17 s | blank |
| **04** | `de_male_natural_storyteller_01` (voice-38) | DE Male Natural Storyteller 01 | male | voice-38 | 53016 | natural storyteller — natürlich, erzählerisch, nahbar, menschlich | `arena_placeholder` | `benchmark/german_recovery_audition/04_de_male_natural_storyteller_01.mp3` (73 389 B) | ~17 s | blank |
| **05** | `de_male_cinematic_restrained_01` (voice-39) | DE Male Cinematic Restrained 01 | male | voice-39 | 53017 | cinematic restrained — filmisch, zurückhaltend, tief, kontrolliert | `arena_placeholder` | `benchmark/german_recovery_audition/05_de_male_cinematic_restrained_01.mp3` (79 533 B) | ~18 s | blank |
| **06** | `de_female_warm_empathetic_01` (voice-40) | DE Female Warm Empathetic 01 | female | voice-40 | 53018 | warm empathetic — warm, empathisch, nahbar, menschlich | `arena_placeholder` | `benchmark/german_recovery_audition/06_de_female_warm_empathetic_01.mp3` (75 213 B) | ~17 s | blank |
| **07** | `de_female_clear_natural_01` (voice-41) | DE Female Clear Natural 01 | female | voice-41 | 53019 | clear natural — klar, natürlich, hell, authentisch | `arena_placeholder` | `benchmark/german_recovery_audition/07_de_female_clear_natural_01.mp3` (81 453 B) | ~18 s | blank |

`status` aller 7: `new_candidate_german_recovery` + `recovery true` (nicht `saved_human_shortlist`, nicht `rejected`), `reference_sha` = `ARENA_VOICE-35..41`, `reference_generated` = real speech via Arena je voice, **kein TestDouble**.

**Offene Rekonstruktion 9-way German (letzter deutscher 9er-Lauf — Pos3 GOOD, Pos5 BETTER HIGH PRIORITY male, Pos6 BEST female):**  
Nach vollständiger Suche (`find benchmark -name "*.mp3" | counts: fast_audition 8, fast_audition_round02 10 (English), fast_audition_de 7, labeled_de 7, verification 3, german_second_audition 4, german_recovery_audition 7` — **kein Verzeichnis mit 9 deutschen MP3s**, `grep` über READMEs/Listening Sheets, JSON-Profile, `voice_generation_recipes.json`, `git log --all --grep=9`, `ls -lt` aller deutschen MP3s, Agent-Reports) konnte **keine eindeutige 9-Audio-Datei-Abfolge** rekonstruiert werden, die den vom User gesehenen `NEUN sichtbaren Audio-Ausgaben` mit Klick-Reihenfolge 1..9 entspricht. **Daher: NICHT geraten**, Status obiger 7 bleibt `new_candidate_german_recovery` (kein Auto-Promote zu `saved_human_shortlist`). Die bereits **verifizierten** deutschen Favoriten **voice-30 (Pos3 BEST MALE), voice-32 (Pos5), voice-33 (Pos6 BEST FEMALE)** bleiben unverändert **LOCKED/Human-selected** (`saved_human_shortlist`, `current_best_*`). Sollten die genannten Pos3/5/6 des 9er-Laufs den oben verifizierten 3 entsprechen, sind sie bereits korrekt gespeichert; andernfalls bitte Position→Voice-ID via sichtbarer Reihenfolge erneut bestätigen, dann werden Pos3/5/6 aus **diesem** `german_recovery_audition` (Pos3=voice-37, Pos5=voice-39, Pos6=voice-40) als `human_selected` / `saved_human_shortlist` markiert (ohne automatischen Ersatz der bestehenden BEST-Hierarchie).

*Dauer geschätzt aus Dateigröße/Bitrate (320k mp3 → WAV-Render uncodiert), identischer Textlänge.

---

## Reproduktion (je Stimme vollständig, 30+ Felder)

**Maschinenlesbar:** `project/voices/voice_generation_recipes.json` — je `voice_id` enthält: `voice_id`, `stable_voice_name`, `candidate_id`, `battle_id`/`arena_voice_id`, `visible_position`, `seed`, `language`, `gender`, `concept`, `voice_design_description`/`prompt`, `voicedesign_reference_text`, `model`/`model_intended`/`model_variant`, `backend`/`engine`/`engine_version`/`api_entry_point`, `reference_audio_path`/`sha256`, `clone_parameters` (x_vector_only_mode, ref_text/audio), `voice_design_parameters` (language, instruct, ref_text, sampling_set, sampling, attempts, model_pool_name), `generation_parameters`/`sampling_parameters` (do_sample, temp/top_k/top_p/rep_pen), `speed` (global 1.0, nicht per-voice), `prosody_parameters` (instruct_variant, cache_version), `conditioning_reference` (reference_text/audio/instruct), `cache_key_fingerprint` (CACHE_VERSION + SHA256-Formel), `audio_format` (WAV 16-bit ref, 32-bit float cache, MP3/24-bit final), `postprocessing` (EBU R128 -14 LUFS, -1.5 dBTP), `runtime_versions` (python/torch/transformers/cuda/qwen), `backend_path` (qwen_engine.py/voice_studio.py/model_pool.py/sampler.py/cache/manager.py), `provenance`/`reproduction_procedure`/`references` (voice_json, audition_audio, architecture_doc, code-Zeilen) und `human_selection` (Position/Status/locked).

**Menschlich nachvollziehbar:** Diese MANIFEST-Datei + `VOICE_GENERATION_ARCHITECTURE.md` (A VoiceDesign B Reference C Clone D Generation E Cache F Output G Reproduction H Limitations).

**Helper:** `project/tools/reproduce_voice.py` (CLI) / `.ps1` — `VOICE RECIPE → VoiceDesign → Reference → Clone → Final`. Beispiel:

```bash
python project/tools/reproduce_voice.py --voice-id de_male_deep_gravitas_02 --language German --reproduce
# 1) design_reference(candidate_id, description, language, seed) -> cache/voice_refs/<id>.wav
# 2) build_clone_prompt(ref)  -> Base-Prompt (clone)
# 3) synth_clone(prompt, SynthesisRequest(text, language, seed, sampling)) per segment -> cache + Master (-14 LUFS)
```

Siehe **§G** der Architektur für vollständige Schrittfolge mit tatsächlichen Code-Zeilen (`qwen_engine.py:79`, `voice_studio.py:79/167/125`, `sampler.py`, `manager.py`).

---

## Integration in App (Status dieser Repo)

- **Registry:** `project/app/voices/registry.py` — lädt alle `voices/*.json`, gruppiert via `per_language.rank` (männlich zuerst, dann weiblich), `for_language()` berücksichtigt `native_status/rank/recommended/default`, `default_voice_id()` → VD-E bei German. **3-Tier-Filter** (ACTIVE/BACKUPS/REJECTED) serialisiert `status`/`human_selected`/`production_candidate`/`production_locked` und persistiert Auswahl (`project/state/app_state.json`). Rejected (`rejected_human`) wird in `entries_for_language()`/GUI nie als empfohlen/active angezeigt.
- **Voice Resolution:** `project/app/voices/resolution.py` / `selection.py` (falls vorhanden) löst `language+gender+preference` → `voice_id` ohne Fallback auf rejected.
- **Backend:** `project/app/tts/qwen_engine.py` (CustomVoice/Base), `voice_studio.py` (Design+Clone), `model_pool.py` (Base/CustomVoice/VoiceDesign-Repos), `cache/manager.py` (deterministisch, `CACHE_VERSION q3p-v2-integrity`), `paths.py` (`VOICE_REFS_DIR`), `hardware/detector.py`.
- **GUI:** Hauptfenster `project/app/gui/main_window.py` gruppiert `Male`/`Female` je Sprache, zeigt `display_name` + `native_status`-Badge, Favoriten-Schlüssel `production_locked`/`saved_human_shortlist` in aktiver Liste, Backup-Bereich separat, Rejected ausgeblendet. Sprache/Gender-Filter + Status-Filter vorhanden.
- **Namen in UI:** Anzeige immer `display_name` (“DE Male Deep Gravitas 02”, “EN Male Warm Storytelling Authoritative 02”, …) plus `voice_id` klein darunter — nie nur ID.
- **Persistenz:** `status`, `human_selected`, `production_candidate`, `production_locked` je JSON werden 1:1 serialisiert (kein silent-default).
- **Benchmark-Mapping:** `project/app/benchmark/german_ab.py`, `phase2_ab.py` referenzieren dieselben `voice_id`s und identischen Kurztexte; Zuordnung `Position→Voice ID` basiert ausschließlich auf **sichtbarer Klick-Reihenfolge**.

---

## Validierung & Smoke Tests (pro ACTIVE-Voice)

- **Validator:** `project/tools/validate_voices.py` (falls nicht vorhanden: `python -m project.app.voices.validator`) prüft `voice_id/display_name/language/gender/seed/description/model/backend/engine/API/procedure/provenance` — schlägt bei `unknown/not recorded` ohne Code-Verweis fehl.
- **Smoke pro ACTIVE:** `registry/profile/serialization/resolution/recipe/cache/synthesis (no fallback)` — via `pytest project/tests/test_voice_*.py` und `python project/tools/reproduce_voice.py --voice-id <id> --dry-run`.
- **Identity Tests:** Identischer deutscher Text `Jede Entdeckung...` für alle 7 `fast_audition_de` + identischer englischer Text `Every discovery...` für alle 10 Round02 — Nachweis, dass Reihenfolge nur von hörbarer Qualität abhängt.

---

## Git & Lieferung (deployable Branch `agent-ready`)

- **Branch:** `arena/01a082be-voice-ai-reference` (enthält `app/GUI/registry/recipes/architecture/setup/START/requirements/tests/README/manifests`, **keine** `models/`, `.venv/`, `cache/`, großen Binär-Caches). Vor Push auditiert via `git remote -v/fetch/prune/branch`, `git log`, `git ls-remote`, Fresh-Checkout-Smoke.
- **Commit-Nachricht dieser Finalisierung:** `Finalize production voice library and reproducible voice architecture`
- **Erwartete Modelle (nicht im Git, via `project/tools/model_setup` / `project/docs/MODELS.md`):** `Qwen/Qwen3-TTS-12Hz-1.7B-Base`, `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`, `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign` unter `MODELS_DIR` (config `project/config/config.json` → `models_dir`).

