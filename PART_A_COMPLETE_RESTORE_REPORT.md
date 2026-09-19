# PART A – COMPLETE READY – Status Report

**Branch:** `reconstruction/part-a-complete`
**Date:** 2026-09-19
**Voice Draft = EXCLUDED** (separates Eigentum des Benutzers, wird nicht erwartet).

## Was in diesem Paket enthalten ist

1. **Vollständiger App-Code**: GUI (`project/app/gui/`, `project/desktop.py`), TTS/Qwen-Engine (`project/app/tts/qwen_engine.py`, `model_pool.py`, `voice_studio.py`), Runner (`project/app/jobs/runner.py`), Jobs/Pipeline, Audio-Mastering, QC/Gates, Segmentierung, Prosodie (classic/semantic/flow/narrative), DE-Fachbegriffe, Reference-Bundle-Architektur, Kontinuitäts-State.
2. **Installations-/Startskripte** (einziges Einstiegsmodell):
   - `SETUP.ps1` – richtet Python/.venv, installiert Abhängigkeiten, prüft CUDA/Torch, sucht Modelle, **startet automatisch** den Frozen-Backup-Import (nur lesend) und abschließenden Voice-Ref-Check.
   - `START.ps1` / `START.bat` – starten GUI / Desktop-Modus.
   - `project/install.ps1` – Modell-Download (Qwen3-TTS-12Hz-1.7B-Base / CustomVoice / VoiceDesign), Multi-Root-Discovery (R:\ etc.).
3. **Tools** (50+): `materialize_references.py`, `bootstrap_reference_bundles.py`, `verify_voice_refs.py`, `test_reference_bundle.py`, `test_pause_strategies.py`, `test_gui_voice_groups.py`, `test_german_pronunciation.py`, `test_hardware_api.py`, `controlled_short_run.py`, `pause_audit.py`, `voice_inventory.py`, `reproduce_voice.py`, Phasen-3/4-Benchmarks, PowerShell-Runner (`run_phase4_*.ps1`, `test_explicit_marker_mode.ps1`).
4. **Voice-Profile**: 50 JSON-Profile unter `project/voices/` (inkl. `en_male_ultra_deep_calm_resonant_01`, aller deutschen Stimmen, VD-E, CustomVoice-Sprecher Ryan/Aiden/Dylan/Serena/Sohee/Uncle_Fu/Vivian).
5. **Golden Reference**: `project/VD-E_GOLDEN_REFERENCE/VD-E.wav` + Runtime-Kopie `project/cache/voice_refs/VD-E.wav`, SHA-256 `b156c02a60a873ad95fc92390c4a136c85308b20188373cd734bee5e5e5f2025` (unverändert, durch Import-Skript und Verify-Tool gegen SHA-Soll geschützt).
6. **Achtundachtzig Audition-/Benchmark-Audios** (MP3/WAV) unter `project/benchmark/fast_audition*`, `project/benchmark/labeled_de`, `project/benchmark/german_recovery_audition` usw.
7. **Frozen-Backup-Importer** (`project/tools/import_voice_refs_from_frozen_backup.ps1`): einmaliges, nur-lesendes Kopieren aus `C:\Users\johan\OneDrive\Desktop\fertige projekte\TEST Apps\VoiceOverApp_STAND_A_PHASE2_20260919_061843\project\cache\voice_refs` nach `project\cache\voice_refs`, inkl. SHA-Prüfung der Golden Reference, ohne den Frozen Backup jemals zu verändern (kein Schreibzugriff auf Quelle).
8. **Voice-Ref-Verifier** (`project/tools/verify_voice_refs.py --strict`): prüft jede Stimme auf Existenz der WAV, 24 kHz mono 16-bit-Format, Sidecar-Manifest, VD-E-SHA, und teilt fehlende Produktions- von lediglich nicht-produktiven (rejected/test-) Stimmen.
9. **Modelle**: NICHT im Git (mehrere GB), aber `install.ps1` lädt sie reproduzierbar von HuggingFace; Multi-Root-Discovery (R:\, `VOICEOVER_MODELS_DIR`) ist bereits in `fix/headless`-Code eingebaut; Offline-Betrieb nach dem ersten Download.

## GUI Stimmen-Gruppierung (geprüft)

Die GUI-Logik in `project/app/gui/voice_view.py` teilt wie folgt ein:
- `locked` → **VD-E** (immer auswählbar)
- `custom` → CustomVoice-Sprecher (Ryan/Aiden/… → KEINE Ref-WAV benötigt)
- `clone` → ACTIVE/BACKUPS (produktionsreif, wenn Ref-WAV vorhanden)
- `candidates` → UNASSESSED/REJECTED (sichtbar aber nicht auswählbar)

`en_male_ultra_deep_calm_resonant_01` ist im JSON als `status=rejected_human` markiert → wird in der GUI als Kandidat mit Warnung gezeigt, nicht als reguläre Auswahl. Deutsche Stimmen haben alle gültige `language_support`/`native_language`/`per_language`-Einträge und tauchen im German-Sprachbaum korrekt auf.

## Was aktuell (noch) nicht im Git liegt – und wie es hereinkommt

Die Production-Clone-Referenz-WAVs (`cache/voice_refs/<id>.wav`) sind **Host-Materialisierungsprodukte** des VoiceDesign-Laufs (24 kHz mono 16-bit, je ~15–25 s). Sie sind in KEINEM Branch/Tag/Release/Asset/Archiv des Repos oder Workspaces vorhanden (forensische Suche über alle 7 Branches + 1 Tag + Workspace + GitHub ergab 0 Treffer; Git-History zeigt sie nie als hinzugefügt an).

Es gibt **18 Produktions-Stimmen**, deren WAV im Git fehlt (vollständige Liste inkl. erwartetem Pfad/Zweck/Quelle in `MISSING_REQUIRED_ASSETS.json`):

| # | voice_id | Sprache | Status |
|---|---|---|---|
| 1 | de_female_clear_natural_01 | DE | new_candidate_german_recovery |
| 2 | de_female_deep_calm_intelligent_01 | DE | good_archived |
| 3 | de_female_deep_warm_documentary_01 | DE | saved_human_shortlist |
| 4 | de_female_warm_empathetic_01 | DE | new_candidate_german_recovery |
| 5 | de_male_cinematic_restrained_01 | DE | new_candidate_german_recovery |
| 6 | de_male_deep_gravitas_02 | DE | new_candidate_german_recovery |
| 7 | de_male_deep_natural_conversational_01 | DE | saved_human_shortlist |
| 8 | de_male_intellectual_precise_01 | DE | new_candidate_german_recovery |
| 9 | de_male_natural_storyteller_01 | DE | new_candidate_german_recovery |
|10 | de_male_warm_calm_authoritative_02 | DE | new_candidate_german_recovery |
|11 | de_male_warm_storytelling_authoritative_01 | DE | saved_human_shortlist |
|12 | en_male_deep_authoritative_scholar_01 | EN | saved_human_shortlist |
|13 | en_male_deep_clear_insightful_01 | EN | saved_human_shortlist |
|14 | en_male_extremely_natural_deep_conversational_01 | EN | saved_human_shortlist |
|15 | en_male_mature_documentary_natural_01 | EN | saved_human_shortlist |
|16 | en_male_velvet_baritone_01 | EN | locked_human_favorite |
|17 | en_male_warm_grounded_humanist_01 | EN | saved_human_shortlist |
|18 | en_male_warm_storytelling_authoritative_02 | EN | locked_human_favorite |

Hinzu kommen 24 als `test_voice_premium_10` / `test_voice` / `rejected_human` klassifizierte Stimmen, die nicht produktionsrelevant sind.

Diese 18 Dateien werden **automatisch** auf zwei Wegen geholt – der Benutzer muss keine WAVs manuell zusammensuchen:

1. **(empfohlen, schnell)** Einmal auf dem Windows-PC `SETUP.ps1` ausführen. Es ruft automatisch `import_voice_refs_from_frozen_backup.ps1` auf, das den Frozen Backup **nur lesend** durchsucht und alle vorhandenen WAVs + Sidecar-Manifeste nach `project\cache\voice_refs\` kopiert (SHA-Prüfung für VD-E, Zählung, Fehlermeldung bei Abweichung).
2. **(Fallback, falls Frozen Backup nicht mehr erreichbar)** Auf dem RTX-5060-Host im Projektverzeichnis:
   ```powershell
   .\SETUP.ps1
   python project\tools\materialize_references.py --all-missing
   ```
   Das erzeugt jede fehlende Referenz per VoiceDesign auf Basis des in `settings.seed`/`settings.variant` festgehaltenen Rezepts und schreibt gleichzeitig das atomare `.wav.json`-Sidecar-Manifest.

Sobald dieser Schritt einmal durchgelaufen ist, ist der Teil-A-Download in sich geschlossen; `verify_voice_refs.py --strict` exits 0, `START.ps1` kann die GUI mit allen Produktionsstimmen öffnen.

## Echter RTX-5060-Test (muss auf dem Host laufen)

Die Sandbox hat keine CUDA-fähige GPU und keine Modellgewichte; Audio-Rendering kann hier nicht stattfinden. Das abschließende PASStesten erfordert auf dem Windows/RTX-5060-Host nach dem Import:

```powershell
# 1. Entpacke VoiceOverApp_PART_A_COMPLETE_READY_<date>.zip in NEUEN leeren Ordner
# 2. Darin:
Set-ExecutionPolicy -Scope Process Bypass
.\SETUP.ps1                                  # Python + Deps + Modelle + Auto-Import
python project\tools\verify_voice_refs.py --strict
.\START.ps1                                  # GUI
python project\tools\controlled_short_run.py --voice en_male_warm_storytelling_authoritative_02 --language English --preset narrative_documentary
python project\tools\controlled_short_run.py --voice vd_e --language German --preset narrative_documentary
python project\tools\controlled_short_run.py --voice de_male_warm_storytelling_authoritative_01 --language German --preset narrative_documentary
python project\tools\test_reference_bundle.py
python project\tools\test_pause_strategies.py
python project\tools\test_gui_voice_groups.py
```

Solange dieser Host-Test nicht durchgeführt wurde, ist PART A **INCOMPLETE** (Code-seitig fertig, letzte Host-Validierung ausständig).

## Status

### Vorläufiger Sandbox-Stand (vor Host-Audio-Test)

```
PART_A_STATUS               = INCOMPLETE  (awaiting host voice-ref import + RTX-5060 audio test)
VOICE_DRAFT                 = EXCLUDED
REQUIRED_ASSETS_COMPLETE    = FAIL        (18 production-clone ref WAVs not in git, reachable via frozen-backup import OR materialize)
VOICE_PROFILES              = 50/50
VOICE_REFERENCE_WAVS        = 1/19  (VD-E OK, 18 production + 24 non-production wavs to be imported/materialized)
VOICE_REFERENCE_MANIFESTS   = 0/19  (produced by bootstrap_reference_bundles.py / materialize_references.py on host)
GUI_RUNTIME_VOICES          = 50/50 (registry loads all; selectability gated by voice-ref availability at runtime)
GOLDEN_REFERENCE            = PASS  (sha b156c02a… verified)
MODELS                      = PROVISIONED_BY_SETUP (not in git; install.ps1 downloads reproducibly)
RTX5060_TTS                 = NOT_RUN (requires host)
FRESH_PACKAGE_TEST          = PASS (syntax + offline unit tests + registry + presets + grouping + ref-bundle resolution in sandbox from extracted zip)
FINAL_COMMIT                = <set at package time>
FINAL_PACKAGE               = dist/VoiceOverApp_PART_A_COMPLETE_READY_<date>.zip
FINAL_PACKAGE_SHA256        = <dist/SHA256SUMS.txt, written at package time>
MISSING_REQUIRED_ASSETS     = siehe MISSING_REQUIRED_ASSETS.json (18 production-clone WAVs + sidecars)
USER_MANUAL_COPY_REQUIRED   = NO   (one-click Import via import_voice_refs_from_frozen_backup.ps1 ODER materialize; keine Handkopier-Einzelaktionen nötig)
```

Nach einmaligem Frozen-Backup-Import (oder `materialize_references.py --all-missing`) und erfolgreichem RTX-5060-Audio-Test wird `verify_voice_refs.py --strict` 0 zurückgeben, und der Status wechselt auf COMPLETE. Das Paket ist dafür vollständig vorbereitet (einziger Einstieg `SETUP.ps1` → `START.ps1`, keine versteckten Nachkopierschritte).
