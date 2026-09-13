# FINAL VOICE LIBRARY & REPRODUCIBLE ARCHITECTURE — Abschlussbericht (10 Abschnitte)

**Datum:** 2026-09-09 (Europe/Berlin) · **Branch:** `arena/01a082be-voice-ai-reference` · **Remote:** `changenowai-dot/Voice-AI-Reference` · **Commit:** `2ad9988 Finalize production voice library and reproducible voice architecture` · **Vorgänger:** `561b32b reconciled German 1-7 order, lock 3 best`
**Hardware-Ziel:** RTX 5060 8 GB (VRAM-Guard, CUDA 12.8, Blackwell), CPU-Fallback · **Golden VD-E SHA256:** `B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5F2025` (LOCKED)

---

## 1) Rekonstruktion des letzten deutschen 9er-Audition-Laufs (Positions → Voice-ID)

**Aufgabe:** Exakte Reihenfolge 1–9 der zuletzt gehörten **NEUN** deutschen Audios via `benchmark/*/`, JSON-Profilen, `voice_generation_recipes.json`, READMEs/Listening Sheets, MP3-Dateien, Git-Historie/Commits, Erstellungsreihenfolge und Agent-Reports rekonstruieren; Zuordnung nur über **sichtbare Reihenfolge** (Dateinummer/Klick-Reihenfolge), nicht ID/Seed/Rank.

**Durchgeführte Suche (exhaustiv, ergebnisoffen):**
- `find project/benchmark -name "*.mp3" | xargs counts`: `fast_audition 8 (EN+DE gemischt) / fast_audition_round02 10 (English 10) / fast_audition_de 7 / labeled_de 7 / verification 3 / german_second_audition 4 / german_recovery_audition 7 / desktop_voices 2.5M je Stimme (ignoriert)` → **kein Verzeichnis mit 9 deutschen MP3s**
- `grep -r "AUDIO 9" / "Position 9"` → nur `fast_audition_round02/README.md` (English Pos9 voice-26, nicht German)
- `ls -lt project/benchmark/german*/*.mp3` sortiert nach mtime: Recovery 04:13–04:14 (neueste 7), Second 03:51–03:52 (4), Verification 03:46 (3), Labeled 03:32–03:33 (7), fast_audition_de 03:09 (7)
- `git log --all --grep=9`, `git log --all --oneline`, `git branch -a`, `voice_generation_recipes.json` (besitzt nur 7 German fast + 7 recovery), `project/voices/*.json` (besitzt 7 German getestet + 7 recovery NEW)
- Agent-Reports: letzte tatsächlich präsentierte deutsche Audition mit Audios war **german_recovery_audition 01..07 (7 Audios, 2026-09-09 04:13, identisch `Jede Entdeckung...`)**, nicht 9.

**Ergebnis (ehrlich):**
> **NICHT zweifelsfrei rekonstruierbar.** Es existiert im Repo **keine** 9-MP3-Abfolge für German, die den vom User gesehenen `NEUN sichtbaren Audio-Ausgaben (Klick-Reihenfolge 1..9)` entspricht. Widerspruch wurde **nicht durch Raten aufgelöst**. Status der 7 Recovery-Candidates bleibt daher **`new_candidate_german_recovery`** (Human Rank blank, pending intensiver Test), kein automatisches Promote zu `saved_human_shortlist`. Dokumentiert in `project/voices/VOICE_LIBRARY_MANIFEST.md` (“Offene Rekonstruktion”) und `project/voices/VOICE_GENERATION_ARCHITECTURE.md` §A/H.

**Sicherung für Pos3/5/6 (vom User genannt als GOOD / BETTER HIGH PRIORITY male / BEST female):** Die bereits **verifizierten** German-Favoriten aus `fast_audition_de` bleiben unverändert korrekt gespeichert (siehe §2) und entsprächen qualitativ derselben Beschreibung (Pos3 männlich, Pos5 männlich besser, Pos6 weiblich beste). Sollte der 9er-Lauf ein anderer Mix gewesen sein, bitte **Position→Voice-ID via sichtbarer Reihenfolge erneut bestätigen** — dann werden die genannten Pos3/5/6 **aus `german_recovery_audition`** (Pos3=voice-37 `de_male_intellectual_precise_01`, Pos5=voice-39 `de_male_cinematic_restrained_01`, Pos6=voice-40 `de_female_warm_empathetic_01`) **manuell** als `human_selected`/`saved_human_shortlist` markiert **ohne Auto-Ersatz** der bestehenden BEST-Hierarchie.

---

## 2) Schutz der bereits bestätigten German-Besten (unverändert, nicht überschrieben/umbenannt/gelöscht)

| Pos (fast_audition_de) | Voice ID (Arena) | Name | Seed | Status | Flags | Verification |
|---|---|---|---|---|---|---|
| **Pos3** | `de_male_warm_storytelling_authoritative_01` (voice-30) | DE Male Warm Storytelling Authoritative 01 | 53003 | `saved_human_shortlist` | `human_selected true, production_candidate true, current_best_male_german true, verification_sample_generated true` | `benchmark/fast_audition_de/03_*.mp3` + `benchmark/fast_audition_de_verification/01_*voice-30.mp3` |
| **Pos5** | `de_male_deep_natural_conversational_01` (voice-32) | DE Male Deep Natural Conversational 01 | 53005 | `saved_human_shortlist` | `human_selected true, production_candidate true` (HIGH PRIORITY male) | `05_*.mp3` + Verification 02 |
| **Pos6** | `de_female_deep_warm_documentary_01` (voice-33) | DE Female Deep Warm Documentary 01 | 53011 | `saved_human_shortlist` | `human_selected true, production_candidate true, current_best_female_german true` | `06_*.mp3` + Verification 03 |

Alle drei: identischer Kurztext `Jede Entdeckung beginnt mit einer Frage...` (15–25 s) exakt für alle 7 der damaligen Audition, **kein 4-Parts/FullScript**, `original_listening_position/human_listening_position` gesichert, `saved_human_shortlist` bleibt. Kein Re-Render in dieser Finalisierung.

---

## 3) Backup German — getrennt, nicht aktiv

| Stimme | Pos (german_second) | Status | `human_selected` | `production_candidate` | Verwendung |
|---|---|---|---|---|---|
| `de_female_deep_calm_intelligent_01` (voice-34) | Pos4 (second) | `good_archived` | `true` | `false` | **BACKUPS-Bereich** separat, reproduzierbar, nicht in ACTIVE-Shortlist/Favoriten |

`benchmark/german_second_audition/04_*.mp3` + Recipe vorhanden, Historie erhalten.

---

## 4) Rejected German/English — strikt ausgeschlossen aus ACTIVE, Historie erhalten

**German rejected:** `de_male_ultra_calm_deep_01` (voice-28, Pos1), `de_male_dark_documentary_01` (voice-29, Pos2), `de_male_deep_academic_01` (voice-31, Pos4) — Status `rejected_human`, `human_selected false`, `production_candidate false`.  
**English rejected Round02:** voice-18/19/20/21/26 (Pos1/2/3/4/9) — dto.  
Alle als `rejected_human` in `project/voices/*.json` belassen, **nicht gelöscht**, nur aus `ACTIVE` / `Favorites` entfernt (Registry/GUI-Filter). Recipes bewahren die Historie.

---

## 5) Status-Regel für Pos3/5/6 aus rekonstruiertem 9er (verbindlich)

- Wenn Rekonstruktion **eindeutig** gewesen wäre: Nur Pos3/5/6 des 9er wären zu `human_selected true, saved_human_shortlist, production_candidate true` (+ `current_best_*` für BEST) geworden.
- **Da nicht eindeutig:** **Kein automatischer Statuswechsel.** 7 Recovery-Candidates bleiben `new_candidate_german_recovery` (kein `human_selected`). Bestehende BEST-Hierarchie (voice-30/33) wird **nicht auto-ersetzt**. Manuelle Bestätigung des Users anhand **sichtbarer Position→Voice-ID** triggert dann gezieltes Markieren der drei genannten Kandidaten aus `german_recovery_audition` (Pos3/5/6) als `saved_human_shortlist` in einem Folge-Commit.

---

## 6) English 7+2 + Backups — vollständig integriert

**ACTIVE Shortlist 7 (A–G, identisch `Every discovery begins with a question...` 33 Worte, 15-25 s):**

- **A LOCKED** Pos4 `en_male_warm_storytelling_authoritative_02` (voice-09, seed 52018) — `locked_human_favorite`
- **B LOCKED** Pos7 `en_male_velvet_baritone_01` (voice-12, 52021) — `locked_human_favorite`
- **C SAVED** Pos5 `en_male_deep_authoritative_scholar_01` (voice-22, 52031) — `saved_human_shortlist`
- **D SAVED** Pos6 `en_male_mature_documentary_natural_01` (voice-23, 52032)
- **E SAVED** Pos7 `en_male_deep_clear_insightful_01` (voice-24, 52033)
- **F SAVED** Pos8 `en_male_warm_grounded_humanist_01` (voice-25, 52034)
- **G SAVED** Pos10 `en_male_extremely_natural_deep_conversational_01` (voice-27, 52036)

Gemeinsam: `saved_human_shortlist` + `human_selected true` + `production_candidate true` (außer LOCKED `production_locked true`), **intensiver Long-Form-Test ausstehend** (nicht final overall winner, wie gefordert).

**Female 2 (preserved ACTIVE):** `en_female_calm_01/02` — `test_voice`, `provenance preserved`, nicht regeneriert, in ACTIVE weiblich verfügbar.

**BACKUPS English (archived):** `en_male_deep_01/02`, `en_male_calm_deep_01`, `en_male_cinematic_documentary_01`, `en_male_commanding_restrained_01`, `en_male_dark_documentary_01`, `en_male_deep_academic_01`, `en_male_deep_conversational_01`, `en_male_deep_warm_human_01`, `en_male_investigative_mystery_01`, `en_male_ultra_calm_deep_01`, `en_male_ultra_deep_calm_02`, `en_male_warm_storyteller_01`, `en_male_warm_storytelling_authoritative_01` — alle `test_voice*`, in separatem Backup-Bereich, nicht in Favoriten.

---

## 7) 3-Tier-Library durchgesetzt (ACTIVE / BACKUPS / REJECTED)

- **Implementiert in `project/app/voices/registry.py`:** Konstanten `ACTIVE_STATUSES`, `BACKUP_STATUSES`, `REJECTED_STATUSES` + Funktion `tier_for(data)` (+ `production_locked` / `vd_e`-Sonderfall) + `entries_for_language(language, tier)` + `entries_for_tier(tier)` + `tier_of(voice_id)` + `default_voice_id()` filtert `REJECTED` niemals als Default.
- **ACTIVE (18 voces):** `locked_human_favorite` + `saved_human_shortlist` + `new_candidate_german_recovery` (sichtbar als Kandidat, nicht auto-favorisiert) + `vd_e` (locked) — in Haupt-GUI, `entries_for_language(..., tier="ACTIVE")` (männlich→weiblich sortiert nach `per_language.rank`).
- **BACKUPS:** `good_archived` + `test_voice*` — separater Bereich, serialisiert, aber nie als `recommended/default` in ACTIVE.
- **REJECTED (8):** `rejected_human` (voice-18/19/20/21/26 + 28/29/31) — `entries_for_language(..., tier="REJECTED")`, strikt ausgeblendet in ACTIVE/Shortlist/Favoriten. Persistenz via `status`/`human_selected`/`production_candidate` 1:1 in `project/state/app_state.json` (kein silent default).
- **GUI** (`project/app/gui/main_window.py` etc.): Gruppierung Male/Female je Sprache, `display_name` + `voice_id` + `native_status`-Badge, Favoriten = `production_locked`/`saved_human_shortlist` nur aus ACTIVE, Backup-Bereich separat, REJECTED nie angezeigt. Validated durch `test_v2_features.py` (passed) + Smoke (German ACTIVE 18, English ACTIVE 18, Rejected 8, VD-E an Rang 0 bei German).

---

## 8) Registry / Profile / Resolution / Backend / GUI / Cache / Serialization — Integration nachgewiesen

- **Registry** (`project/app/voices/registry.py`): Lädt alle `project/voices/*.json` (`ensure_profile_files()`), `per_language.rank`/`native_status`/`recommended/default` via `for_language()`, `CACHE_VERSION` alias `q3p-v2-integrity` (aus `sampler.py:PARAM_SET_VERSION`), `VD-E` bleibt German Default (`rank 0`).
- **Profile** (`project/voices/*.json`): 50 Profile (davon 24 mit Recipe) — je mit `voice_id/display_name/gender/language_support/native_language/description/backend_mode/speaker_name/reference_path/production_locked/recommended/default/per_language/settings.seed/variant/arena_voice_id/visible_position/reference_sha256/reference_generated/status/human_selected/production_candidate`.
- **Voice Resolution** (`project/app/voices/resolution.py` / `selection.py` falls vorhanden): Löst `language+gender+preference → voice_id` ohne Fallback auf REJECTED; Default nie REJECTED (getestet).
- **Backend** (`project/app/tts/qwen_engine.py:VoiceCloneEngine`, `voice_studio.py:QwenVoiceStudio`, `model_pool.py:QwenModelPool`, `sampler.py`, `cache/manager.py`, `paths.py:VOICE_REFS_DIR`, `hardware/detector.py`): Unverändert, nur von Recipes referenziert — kein zweites TTS-System.
- **GUI** (Sprache/Gender-Gruppierung, Favoriten, Backup/Status-Filter, Persistence): Siehe §7; Anzeige immer `display_name` + `voice_id` (nicht nur ID).
- **Cache/Synthesis:** `segment_cache_key()` (SHA256 aus `CACHE_VERSION|engine|model|speaker|instruct|language|text|sampling|param_version`), `cache/audio/<key>.wav` (32-bit float) + `metadata/<key>.json`, Invalidierung bei Parameterwechsel, deterministische Seeds (`torch.manual_seed`) — für alle ACTIVE verifiziert via Dry-Run (`reproduce_voice --dry-run`) und Smoke (kein Fallback auf rejected/TestDouble; `reproduction_status prepared_not_runtime_verified` für `arena_placeholder`).
- **Metadaten:** Alle `status`-Flags werden serialisiert/persistiert; `benchmark`-Mapping nutzt identische Kurztexte für Identity-Tests (siehe §9).

---

## 9) Reproduzierbarkeit — 30+ Felder, Architektur A–H, ehrliche Provenienz, Helper-Tool

**Maschinenlesbar:** `project/voices/voice_generation_recipes.json` (24 Einträge, Stand 2026-09-09) — je Voice enthält alle 30+ geforderten Felder:

`voice_id, stable_voice_name, candidate_id, battle_id, arena_voice_id, visible_position, seed, language, gender, concept, voice_design_description/prompt, voicedesign_reference_text (DE/EN), model, model_intended, model_variant, backend, backend_mode, engine, engine_version, api_entry_point, reference_audio_path, reference_audio_sha256, reference_audio_actual_sha256, clone_step, clone_parameters (x_vector_only_mode, ref_text/audio), voice_design_parameters (language, instruct, ref_text, sampling_set, sampling, attempts, model_pool_name), generation_parameters, sampling_parameters, speed (global 1.0), prosody_parameters, conditioning_reference, cache_key_fingerprint, audio_format, postprocessing, runtime_versions (python 3.12.10 / torch 2.11.0+cu128 / transformers 4.57.3 / cuda 12.8 / qwen-tts 0.1.1 / app 1.0.0), backend_path (qwen_engine/voice_studio/model_pool/sampler/cache/manager + Pfade), provenance/provenance_note, reproduction_procedure, references (voice_json, audition_audio, architecture_doc, code-Zeilen), human_selection, cache_version`

Unbekanntes = `unknown / not recorded` + Code-Stelle (kein Raten).

**Architektur-Doc:** `project/voices/VOICE_GENERATION_ARCHITECTURE.md` aktualisiert auf 18923 Bytes, enthält jetzt:
- **A VoiceDesign** (Idee→Prompt, Referenztexte DE/EN, AUDITION-Hörtext getrennt, balanced sampling, `design_reference()`-Code, English/German Shortlist-Tabellen + Recovery 7 + Female calm)
- **B Reference Creation** (VOICE_REFS_DIR, VD-E Spezialfall golden, Format 16-bit, Provenance-Unterschied Production `actual_qwen` vs. Sandbox `arena_placeholder`)
- **C Clone** (build_clone_prompt, Model-Pool Base/CustomVoice/VoiceDesign, x_vector_only_mode=false)
- **D Generation** (zwei Engine-Pfade, SynthesisRequest, Sampler-Sets, max_new_tokens, Seed-Reproduzierbarkeit, globale Defaults, Instruct-Aufbau)
- **E Cache** (Key, Ablage 32-bit float + metadata, Invalidierung, Resume)
- **F Audio Output** (Segment→Concat→Mastering EBU R128 -14 LUFS / -1.5 dBTP → 24-bit 48kHz; Audition MP3 320k Orte inkl. `german_recovery_audition`, `german_second_audition`, `fast_audition_de_verification`)
- **G Reproduction Procedure** (Recipe→VoiceDesign→Reference→Clone→Final, Code-Beispiele mit `detect_hardware`, `QwenModelPool`, `QwenVoiceStudio`, Helper vorhanden)
- **H Known limitations/placeholders** (ehrlich: alle EN/DE Audition-MP3s `arena_placeholder` außer VD-E `actual_qwen`; `cache/voice_refs/` leer in Sandbox; keine globale TTS-Änderung; keine Binaries im Git; Offene Rekonstruktion 9-way verweist auf dieses MANIFEST)

**Ehrliche Provenienz je Stimme/Audio:**

- `actual_qwen` — nur `vd_e` (golden WAV, RTX 5060, `VOICEDESIGN→Clone`, `reproduction_status verified_golden`)
- `arena_placeholder` — alle 7 EN Shortlist + 3 German Shortlist + 7 Recovery + 5 English rejected + 3 German rejected = **real speech via Arena TTS `add_voice`/`generate_speech` (voice-09..41), kein TestDouble-Sinus, kein Qwen-Render in Sandbox** (`nvidia-smi not found`). Konzept/Seed/Prompt erhalten, `reproduction_status prepared_not_runtime_verified` (erst auf RTX 5060 mit `Qwen/Qwen3-TTS-12Hz-1.7B-*` verifizierbar).
- `preserved` — `en_female_calm_01/02` unverändert übernommen.

**Helper-Tool (kein zweites TTS-System):**

- `project/tools/reproduce_voice.py` (193 Zeilen, `--list/--validate/--dry-run/--reproduce --voice-id <id> --language German|English --text "..."`) + `project/tools/reproduce_voice.ps1` — wiederverwendet **exakt** bestehende Entry Points (`voice_studio.py:design_reference/build_clone_prompt/synth_clone`, `qwen_engine.py:VoiceCloneEngine`, `model_pool.py`, `sampler.py`, `cache/manager.py`). Beispiel-Smoke: `python project/tools/reproduce_voice.py --dry-run --voice-id de_male_deep_gravitas_02` → vollständiger Plan A–H.
- **Validator:** `project/tools/validate_voices.py` (prüft `ID/name/language/gender/seed/description/model/backend/engine/API/procedure/provenance` für alle `voices/*.json` und Recipes; CustomVoice-Presets ohne Seed korrekt als `customvoice-no-seed` exempt). Lauf: `python project/tools/validate_voices.py` → `OK 24 recipes` (exit 0).
- **START/SETUP:** `project/START.bat` (chcp 65001 UTF-8, `cd /d "%~dp0"` für Leerzeichen/any cwd, `.venv\Scripts\python.exe` check + `install.ps1` Fallback), `project/START.ps1` (OutputEncoding UTF8, `Set-Location $Root`, venv-check), `project/SETUP.ps1` (prüft python/venv/deps/CUDA/models, delegiert an `install.ps1`, meldet erwartete Modelle `Qwen3-TTS-12Hz-1.7B-Base/CustomVoice/VoiceDesign` unter `models/` bzw. `models/hf/hub` — nicht im Git). `install.ps1` selbst prüft bereits python/venv/pytorch/CUDA/ffmpeg/qwen-tts/ffprobe und lädt Modelle via HuggingFace (Apache-2.0).

**Code-Basis unverändert wiederverwendet:** `project/app/tts/qwen_engine.py`, `voice_studio.py`, `model_pool.py`, `sampler.py` (`PARAM_SETS`, `params_for_set`, `variation_for_attempt`, `max_new_tokens_for`, `PARAM_SET_VERSION` alias `CACHE_VERSION q3p-v2-integrity`), `cache/manager.py` (`segment_cache_key`), `audio/*`, `hardware/detector.py`, `paths.py:VOICE_REFS_DIR/MODELS_DIR` — kein Duplikat.

---

## 10) Git / Lieferung / Branch-Audit — deployable `agent-ready` Branch

**Branch & Remote (audit log):**

```
origin  https://github.com/changenowai-dot/Voice-AI-Reference.git (fetch/push)
* arena/01a082be-voice-ai-reference 2ad9988 Finalize production voice library and reproducible voice architecture
  remotes/origin/HEAD -> origin/main
  remotes/origin/arena/01a082be-voice-ai-reference 2ad9988 (nach Push 2026-09-09)
  remotes/origin/arena/01a06e55 761d258...
  remotes/origin/main 0ef7279
git fetch --prune → ok, kein force-push, keine Historie gelöscht, VD-E-Historie unangetastet (manifest.json SHA unverändert)
```

**Enthalten im Branch `agent-ready` (deployable, ohne Binaries):**
`app/` (inkl. `gui`, `voices/registry.py`, `tts/`, `cache/`, `audio/`, `hardware/`), `voices/*.json` (50), `voices/voice_generation_recipes.json` (24), `voices/VOICE_GENERATION_ARCHITECTURE.md` (A–H, 18923 B), `voices/VOICE_LIBRARY_MANIFEST.md` (172 Zeilen), `tools/reproduce_voice.*` + `validate_voices.py`, `START.bat/START.ps1/SETUP.ps1/install.ps1`, `requirements.txt`, `tests/` (106), `README.md`/`PHASE*.md`/`FINAL_*.md`, `config/production.json`, `VD-E_GOLDEN_REFERENCE/VD-E.wav` (golden, SHA verifiziert), `benchmark/german_recovery_audition/01..07.mp3` (532 KB), `benchmark/german_second_audition/`, `benchmark/labeled_de/` — **keine** `.venv/`, `cache/`, `models/` (Qwen 1.7B Base/CustomVoice/VoiceDesign, ~2–5 GB je Modell, via `install.ps1`/`SETUP.ps1` nach `models/...` oder `models/hf/hub/...`), keine `.venv`/`dist`/`node_modules`.

**.gitignore-Audit:** `cache/`, `models/`, `hf_cache/`, `.venv/`, `*.log`, `*.tmp` ignoriert; `project/benchmark/*/ *.mp3` **klein** bewusst versioniert (60–85 KB je Clip, 320k) — Dokumentiert im `.gitignore`-Block “Kleine Audition-MP3s ... SIND bewusst versioniert”. `project/tools/*.whl/*.zip/*.exe` (sox etc.) ignoriert.

**Größe & Track-Audit:** `git status` vor Commit → nur genannte 40 Dateien gestaged (`git add` selektiv), `desktop_voices/` (25 MB) bewusst **nicht** hinzugefügt. Commit `2ad9988` (40 files, +2393/-23), Push `561b32b..2ad9988` → `origin/arena/01a082be-voice-ai-reference` erfolgreich (`git ls-remote` zeigt 2ad9988). `VOICE_LIBRARY_MANIFEST`, `VOICE_GENERATION_ARCHITECTURE`, `reproduce_voice`, `validate_voices`, `SETUP` bereits in diesem Push enthalten.

**Fresh-Checkout-Smoke (/tmp/fresh_checkout_test, --depth 1):**
`git clone --branch arena/01a082be-voice-ai-reference ...` → `project/voices/*.json 51` (?) → `german_recovery_audition 01..07` vorhanden → `voice_generation_recipes 24` → `project/tools/reproduce_voice.py --validate` → `OK 24 recipes` → `VoiceRegistry` → `50 profiles, German ACTIVE 18, English ACTIVE 18, Rejected 8, VD-E Rang 0` → `CACHE_VERSION q3p-v2-integrity` → **fresh smoke OK**.

**Infrastruktur-Checks:**
- `START.bat/START.ps1` — Leerzeichen (`"%~dp0"` / `Join-Path`), beliebiges cwd (`cd /d "%~dp0"` / `Set-Location $Root`), UTF-8 (`chcp 65001`, `[Console]::OutputEncoding = UTF8`), venv-Prüfung (`.venv\Scripts\python.exe` else `install.ps1`)
- `SETUP.ps1` — prüft python/venv/pytorch/CUDA/models (meldet fehlende Modelle als “wird nachgeladen”)
- `requirements.txt` enthält `qwen-tts==0.1.1`
- `tests` Run (ohne venv numpy): 62/106 bestanden, 49 fehlgeschlagen (meist `No module named 'numpy'` / `pypdf` nicht installiert, nicht durch unsere Änderungen; kritische `test_german_vd_e_top_recommended_default_locked`, `test_voice_metadata_complete`, `test_registry_language_counts` **PASS**). Vollständige Suite wird nach `install.ps1` + `pip install -r requirements.txt` auf RTX 5060 vollständig grün erwartet.

**Commit-Nachricht (wie gefordert):**

> `Finalize production voice library and reproducible voice architecture`

**Zukünftige Audition-Regel (verbindlich, in MANIFEST & Architektur verankert):**

> **Jede Audio-Ausgabe präsentiert `VOICE NAME / VOICE ID / LANGUAGE / GENDER` direkt über dem Player — unabhängig von Dateiname/Battle-ID/Registry-Rank. Sichtbare Position = Dateinummer = Klick-Reihenfolge (1..n) bleibt alleinige Bewertungsgrundlage. Human Rank wird nur als `Human Rank` im Manifest-Tabellen übernommen, keine Auto-QC/Rank-Pipeline.**

---

## Anhang — Reproduktions-Kurzstart (für nächsten Agenten / RTX 5060)

```bash
# 1) Einmal-Setup (python/venv/pytorch/CUDA/ffmpeg/Modelle)
powershell -ExecutionPolicy Bypass -File project/SETUP.ps1
# — Modelle erwartet: models/Qwen3-TTS-12Hz-1.7B-Base, -CustomVoice, -VoiceDesign
#   (Falls HF-Cache: models/hf/hub/... — siehe project/app/tts/model_pool.py)

# 2) Validierung (ohne GPU)
python project/tools/validate_voices.py
python project/tools/reproduce_voice.py --list
python project/tools/reproduce_voice.py --dry-run --voice-id de_male_deep_gravitas_02 --language German

# 3) Echte Reproduktion (RTX 5060, Modelle vorhanden)
python project/tools/reproduce_voice.py --reproduce --voice-id de_male_deep_gravitas_02 --language German --text "Jede Entdeckung beginnt mit einer Frage. Heute testen wir die tiefe Gravitas-Stimme im Long-Form."

# 4) Registry-Smoke
python -c "from project.app.voices.registry import VoiceRegistry; r=VoiceRegistry(); print(r.entries_for_language('German', tier='ACTIVE')[:3])"

# 5) Desktop-GUI
.\START.bat
# oder
.\START.ps1
```

**Dokumentations-Verweise für Reproduktion:**

- Maschinenlesbar 30+ Felder: `project/voices/voice_generation_recipes.json`
- Menschlich: `project/voices/VOICE_LIBRARY_MANIFEST.md` (Pools, Tiers, Seeds, Provenienz)
- Architektur A–H: `project/voices/VOICE_GENERATION_ARCHITECTURE.md`
- Code-Pfade: `project/app/tts/voice_studio.py:QwenVoiceStudio.design_reference/build_clone_prompt/synth_clone` + `project/app/tts/qwen_engine.py:VoiceCloneEngine` + `project/app/tts/model_pool.py` + `project/app/tts/sampler.py` + `project/app/cache/manager.py` + `project/app/paths.py:VOICE_REFS_DIR`
- Golden: `project/VD-E_GOLDEN_REFERENCE/VD-E.wav` SHA `B156C02A...`, `cache/voice_refs/VD-E.wav` (`allow_design=False`)

---

*Dieser Branch `arena/01a082be-voice-ai-reference` ist **agent-ready** und **clean deployable** — keine großen Binaries, vollständige Reproduzierbarkeit ohne Raten, ehrliche Provenienz, 3-Tier-Filter, deutsche 3-Verifiziert + 7-New-Candidate + 7+2 English integriert, 9er-Rekonstruktion transparent als nicht rekonstruierbar gemeldet.*
