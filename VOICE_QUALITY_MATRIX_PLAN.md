# Voice Quality Matrix — Phase 1..7 Plan

HEAD: `5c430f3ec04cf712ad88ee871f60bc6c635dae9f`
Reference quality voice: `en_male_warm_storytelling_authoritative_02` (commit 5c430f3 — proven working long-form).

## Goal

Bring every selectable voice to the same production-quality standard
as `en_male_warm_storytelling_authoritative_02` without homogenising
identity, timbre, gender or language. Do not touch VD-E Golden. Do not
regress protected voices. No silent fallbacks. Human listening is the
final authority; automated metrics are diagnostic only.

## New tooling added in this change

`project/tools/voice_inventory.py`
  - `--static` → build inventory (registry + bundle resolution); runs
    anywhere, no torch/GPU required.
  - `--short` → ~5–10 s synthesis per voice using a controlled
    language-matched short text, writes 24-bit WAV + records duration,
    RMS, peak, NaN, elapsed.
  - `--spot 60` → run a ~60 s segmented long-form pipeline on voices
    that pass short, records regeneration count, failed segments,
    average QC score.
  Outputs: `project/benchmark/voice_inventory/inventory.json` (machine)
  and `INVENTORY.md` (human).

## Voice inventory summary (static, from sandbox — no WAVs present)

| Category           | Count | Notes                                                     |
|--------------------|------:|-----------------------------------------------------------|
| Total registered   |    50 | `app.voices.registry.VoiceRegistry().entries()`           |
| CustomVoice        |     7 | Aiden, Ryan, Dylan, Uncle_Fu, Serena, Vivian, Sohee       |
| Clone              |    43 | VD-E + 3 EN test + voice-09 locked + 38 premium/recipe    |
| Production locked  |     3 | vd_e, en_male_velvet_baritone_01, en_male_warm_storytelling_authoritative_02 |
| Clone WAV present  |     0 | (sandbox — materialized WAVs live on the RTX 5060 host)   |

After Phase 1 the report lists every voice with backend, language,
seed, bundle status, audio_sha256, text_sha256 and classification.

## Execution sequence on the RTX 5060 host

```bash
# 0. Get the code
git pull --ff-only                            # -> 5c430f3
git rev-parse HEAD                           # expect 5c430f3e…

# 1. Static inventory (no model load)
python project/tools/voice_inventory.py --static

# 2. Repair the known voice-09 sidecar if you haven't already
python project/tools/bootstrap_reference_bundles.py --dry-run
python project/tools/bootstrap_reference_bundles.py

# 3. Materialize any clone voices whose canonical WAV is still missing.
#    The inventory shows which ones are WAV_MISSING. For each:
python project/tools/materialize_references.py \
    --voice-id <voice_id> --language English   # or German
#    (VoiceDesign requires Qwen3-TTS-12Hz-1.7B-VoiceDesign model.)

# 4. Short synthesis matrix (loads models, ~2-4 min total)
python project/tools/voice_inventory.py --static --short

# 5. Spot long-form for voices that pass short (~10-30 s per voice)
python project/tools/voice_inventory.py --static --short --spot 60

# 6. Inspect the report
cat project/benchmark/voice_inventory/INVENTORY.md
```

## What Phase 2 (pipeline consistency) verifies per voice

Already implemented in `inspect_static()` inside
`voice_inventory.py` and in the ReferenceBundle resolver:

- `voice_id` resolves in `VoiceRegistry`
- `backend_mode` matches expectation (customvoice/clone)
- language derived from profile / voice-id prefix (en_→English,
  de_/vd_e→German); never silent default
- canonical WAV path is `cache/voice_refs/<id>.wav` (not an ad-hoc path)
- `resolve_bundle()` either returns a valid bundle or raises a precise
  BundleResolutionError code (AUDIO_MISSING / MANIFEST_MISSING /
  AUDIO_SHA256 / TEXT_SHA256 / AMBIGUOUS / LANGUAGE / PROVENANCE_UNPROVABLE)
- reference bundle audio_sha256 / text_sha256 / seed captured
- deterministic seed recorded (voice JSON settings.seed or recipe seed)
- CustomVoice voices have `speaker_name` set and are routed through
  `QwenTTSEngine.generate_custom_voice`
- no silent fallback at any layer (engine asserts REFERENCE_TEXT_MISSING
  if a WAV override is passed without a transcript)

## Short-test methodology (Phase 3)

Same controlled text per language, held constant for all voices:

- English:
  > Every discovery begins with a question. Sometimes the answer is
  > hidden in plain sight, waiting for someone patient enough to look
  > beyond the obvious.
- German:
  > Jede Entdeckung beginnt mit einer Frage. Manchmal liegt die Antwort
  > direkt vor uns, verborgen im Offensichtlichen. Erst wenn wir genau
  > hinschauen, erkennen wir, was wirklich geschah.

Per-voice recorded fields: `duration_s`, `rms`, `peak`, `nan`,
`final_gate` (where applicable), `qc_score`, `retry_count`,
`elapsed_s`, `output` WAV path. NaN/Inf, peak > 1.0, RMS < 0.005, or
duration < 2 s automatically classify as FAIL (needs fix).

## Long-form spot-check (Phase 4)

~60 s of narrative text per language (different from the short test
and different from the VoiceDesign reference text) run through the
production Pipeline with segmentation (350/120/600 chars, balanced
QC, final_gate_ratio 0.88) and ContinuityState enabled. Recorded:
final duration, regenerated segment count, failed segments, average
QC score, output path, elapsed time. Acceptable: no failed segments,
≤2 regenerations. Voices that exceed that go to NEEDS_FIX.

## Phase 5 — Fix policy

For each NEEDS_FIX / BLOCKED voice, apply the MINIMUM change that
addresses the actual cause, preferring in order:

1. Profile metadata error (seed/language/ref_text_key/wrong backend)
2. Missing/incorrect reference bundle (bootstrap or re-materialize)
3. Profile-level sampling / prosody tuning
4. Seed/variant adjustment
5. Last resort: re-design reference via VoiceDesign (requires
   --force; re-materializes WAV + bundle atomically; only when
   provenance explicitly requires it)

Do NOT lower `qc_min_score`, `final_gate_ratio`, disable QC, disable
continuity tracking, or substitute another voice/backend. Do not
regenerate a valid canonical WAV unless provenance is broken.

## Phase 6 — App usability

The GUI groups (Production Locked / Custom Voices / Clone Voices)
already display availability from the registry. After matrix run:
- any voice marked PASS must be selectable and produce output through
  the normal GUI backend (build_engine path in jobs/runner.py)
- any BLOCKED voice stays visible but disabled with the reason from
  `classification_reason` (already wired through `availability_note`)
- no voice silently substitutes another backend

## Phase 7 — Regression gates

After all fixes:

- `python project/tools/test_reference_bundle.py`  (31 tests)
- `python project/tools/test_hardware_api.py`
- `python project/tools/test_longform_unbound.py`
- AST parse all project/*.py
- VD-E SHA unchanged: `b156c02a60a873ad95fc92390c4a136c85308b20188373cd734bee5e5e5f2025`
- `AppContext` engine builds successfully for every PASS voice
- short WAV exists and is non-silent for every PASS voice
- spot WAV exists for every PASS voice

## Deliverable (post-GPU run)

Commit the final `inventory.json` + `INVENTORY.md` + any targeted
profile fixes, then add a summary in a FINAL VOICE MATRIX report
listing every PASS / NEEDS_FIX / BLOCKED voice with the exact reason
and fix applied. Human listening is required for every PASS voice
before signing off.
