# PART A – COMPLETE RECONSTRUCTION REPORT

**Branch:** `reconstruction/part-a-complete`
**Date:** 2026-09-19
**Authorative base:** `origin/arena/01a08d48-voice-ai-reference` @ `0b4d8b5` (Phase 2 prosody / reference-bundle / QA harness)
**Unioned with (additive only):**
- `fix/headless-engine-hw-parameter` (RTX-5060 Phase-4 runners, explicit +++++ marker, headless HW fix, torch/NumPy/installer/identity hardening)
- `feature/explicit-plus-marker-split-mode` (identical head to fix/headless for the same feature set; redundant after union)
- `arena/01a06e55-voice-ai-reference` (Delphi pronunciation tests, `app.cache` module, runtime-ref path fixes)
- `arena/01a082be-voice-ai-reference` (PowerShell 5.1 quoting fix; 01a08d48 supersedes it)
- `agent-ready` (controlled short launcher — already superseded by 01a08d48's own `controlled_short_run.py`)
- `PHASE4_AUDIO_SAFEPOINT_20260906` tag (user-verified GOOD audio baseline checkpoint)
- `main` (initial project + VD-E Golden Reference — VD-E.wav SHA verified identical across ALL branches)

## Sources analyzed

```
git branches (local/remote):
  main
  agent-ready
  arena/01a06e55-voice-ai-reference
  arena/01a082be-voice-ai-reference
  arena/01a08d48-voice-ai-reference  (primary)
  feature/explicit-plus-marker-split-mode
  fix/headless-engine-hw-parameter
tags:
  PHASE4_AUDIO_SAFEPOINT_20260906
releases:
  (none published on GitHub)
release assets: (none)
workspace archives: NONE (no .zip/.7z/.rar/.tar found under /home/user
  outside the repository — confirmed via find /home/user)
Git-LFS: not configured (no .gitattributes, no submodules).
```

## Inventory (consolidated tree)

| Category | Count |
|---|---:|
| Python modules | 157 |
| PowerShell scripts (.ps1) | 15 |
| Batch launchers (.bat) | 6 |
| Benchmark audio WAV/MP3 | 89 |
| Voice JSON profiles | 50 |
| Regression tests | 24 |
| Reports / docs | 43 |
| JSON configs / manifests | 73 |
| **Total files** | **453 tracked** (+ ~11 historical backup files kept verbatim under `project/backup/`) |

## Merge policy

1. **Base = tip of `arena/01a08d48-voice-ai-reference`** (newest complete
   Stage-A codebase: ReferenceBundles, materialize/bootstrap tooling,
   voice-inventory harness, narrative pause strategy, DE
   specialist-term respelling, GUI four-tier grouping).
2. **Union-add** every file that exists on the other branches but NOT
   on base, provided it is a non-conflicting asset (docs, .ps1, .bat,
   audio, test scripts, benchmark helpers, checkpoint metadata,
   recovery/reproduction docs, root launchers).
3. **Overlap policy:** when the same source file exists on multiple
   branches, the base version wins UNLESS it is a Windows launcher
   / install script — those are taken from `fix/headless` (they
   contain the RTX-5060 hardening: stderr handling, Python
   discovery, torch CUDA property compatibility, PowerShell 5.1
   quoting, VOICEOVER_RUNTIME_REF env-var support).
4. **Code compatibility:** Python source files in `project/app/...`
   were NOT copied from older branches on top of the base, because
   those branches predate the reference-bundle/narrative-pause/GUI-
   grouping work and would silently regress Stage-A fixes. Only
   additive Phase-4 tests/benchmark scripts from `fix/headless` were
   added.

## VD-E Golden Reference (protected)

| | |
|---|---|
| Path | `project/VD-E_GOLDEN_REFERENCE/VD-E.wav` |
| SHA-256 | `b156c02a60a873ad95fc92390c4a136c85308b20188373cd734bee5e5e5f2025` |
| Identical across all 8 refs | ✅ confirmed (git object hash `36122e05…` on every branch/tag) |

## Functional/regression test results (sandbox)

```
ALL PAUSE-STRATEGY TESTS PASSED                    (6/6)
ALL GERMAN PRONUNCIATION TESTS PASSED             (7/7)
ALL GUI VOICE-GROUP TESTS PASSED                  (11/11)
ALL REFERENCE-BUNDLE TESTS PASSED                 (31/31)
PASS: production contract (hardware_api)
PASS: score_obj_metrics initialized (longform_unbound)
Python syntax project-wide: 0 errors
split_plan +++++ marker: parts=2 OK                  (Parts intact)
VoiceRegistry loaded: 50 voices                     (all profiles)
presets: 9 (incl. narrative_documentary)
pause strategies: classic / semantic / flow / narrative
continuity / reference_bundle modules import OK
```

## Fresh-package test protocol (run on RTX-5060 host)

```powershell
# 1. Download the zip, extract into a NEW empty folder (no old copies)
# 2. From that folder:
Set-ExecutionPolicy -Scope Process Bypass
.\SETUP.ps1                       # install / verify torch + models
.\START.ps1                       # launch GUI
# Headless smoke:
python project\tools\validate_voices.py --voices
python project\tools\test_reference_bundle.py
python project\tools\test_pause_strategies.py
python project\tools\test_german_pronunciation.py
python project\tools\test_gui_voice_groups.py
# Short production run (no GUI):
python project\tools\controlled_short_run.py `
    --voice en_male_warm_storytelling_authoritative_02 `
    --language English --preset narrative_documentary
# Parts regression:
python project\tools\reproduce_voice.py `
    --voice en_male_ultra_deep_calm_resonant_01 `
    --language English --preset narrative_documentary `
    --input project\benchmark\prosody\phase2_parts_test.txt `
    --output out\parts_test --parts
```

## Known limitations (cannot be completed from the sandbox)

1. **Model weights (Qwen3-TTS-12Hz-1.7B, CustomVoice, VoiceDesign
   candidate)**: NOT stored in Git (multi-GB binaries). They are
   fetched by `install.ps1`/`models/`-Auto-Discovery and must be
   downloaded/cached on the host. The reconstruction does NOT
   invent or fake them; install scripts and multi-root model
   discovery (from `fix/headless`) are included, so the host can
   locate an existing model directory or re-download.
2. **Materialized voice-reference WAVs** (the 43 clone voices in
   `cache/voice_refs/<id>.wav` + sidecar manifests) are host-local
   build artifacts, not repository data. The tools
   `materialize_references.py` and `bootstrap_reference_bundles.py`
   are included so the host can regenerate them; Voice-09's
   canonical WAV already exists on the user's host and will not be
   re-synthesized.
3. **Actual TTS audio output cannot be validated in the sandbox**
   (no CUDA / no models). Audio-quality confirmation requires the
   Fresh-Package step on the RTX-5060 host (protocol above).
4. **Zip creation**: the final ZIP is produced at delivery time in
   this workspace (command below).

## Headline result (pre-ZIP)

- `RESTORE = PASS (archive-ready; host audio-validation pending)`
- `SOURCES_ANALYZED = 7 branches + 1 tag + workspace scan (no archives found)`
- `HISTORICAL_STANDS_FOUND = 8`
- `FILES_CONSOLIDATED = 453 tracked (+ 11 intentional historical backups)`
- `MISSING_REQUIRED_FILES = none that exist in any reachable git
  object`; missing-but-needed assets are the large model weights and
  host-local voice-reference WAVs, both obtainable via the
  install/ materialize tooling that IS present.
- `GOLDEN_REFERENCE = PASS (b156c02a… verified identical across all refs)`
- `FUNCTIONAL_TESTS = see above (syntax + import + all offline unit
  tests pass)`
- `FRESH_PACKAGE_TEST = pending on host (no GPU in sandbox)`

## Build final ZIP from this branch

```bash
git checkout reconstruction/part-a-complete
mkdir -p dist
cd /home/user/Voice-AI-Reference
zip -rq dist/VoiceOverApp_PART_A_COMPLETE_RECONSTRUCTED_$(date +%Y%m%d_%H%M%S).zip \
    . -x '.git/*' '_consolidated_work/*' '_stage/*' '_build_consolidated.py'
sha256sum dist/VoiceOverApp_PART_A_COMPLETE_RECONSTRUCTED_*.zip
```

(The final SHA of the produced ZIP is reported after the zip command;
it will be written into `RESTORE_MANIFEST.json` at package time.)
