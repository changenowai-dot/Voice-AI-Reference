# Production Stabilization — Final Report

Date: 2026-09-15
Branch: `arena/01a08d48-voice-ai-reference`
Status: **STAGE 1 complete & pushed; STAGE 2–7 need host GPU run.**

## Summary

Every GUI-exposed voice now resolves to a valid, decodable reference
(or is explicitly marked unavailable). No voice in the GUI can silently
trigger the VoiceDesign model fallback, so the two symptoms the user
reported are fixed at the routing layer:

- **(A) VoiceDesign model-not-found for GUI selections** → eliminated
  because `runner.py` now gets `allow_design=False` for every
  GUI-selectable clone voice (reference_path → existing file);
  `qwen_engine._ensure_prompt` never reaches `studio.design_reference()`
  and therefore never calls `model_pool.get("voicedesign")`.
- **(B) garbled / non-speech / wrong voice output** → the previous
  garbled outputs came from (i) running VoiceDesign->Base-Clone with a
  *missing* ref and `allow_design=True` against a model that was not
  installed (error paths produced garbage / random prompts) and
  (ii) legacy `cache/voice_refs/*.wav` references that didn't exist.
  Both root causes removed; genuine TTS quality must still be
  verified end-to-end on a GPU host (see Stages below).

## Commits on this branch (most recent first)

| SHA        | What it fixes                                                                 |
|------------|--------------------------------------------------------------------------------|
| `838db39`  | 10 remaining legacy/stale clone voices repointed to existing MP3s; `en_female_calm_01/02` marked `available=false`; runtime `cache/voice_refs/VD-E.wav` seeded from Golden (local only, not committed). |
| `ee6a178`  | 8 fast-audition EN voices corrected from stale `male_deep_candidates/.../part1.mp3` to the actual `benchmark/fast_audition/NN_*.mp3`. |
| `80216f5`  | QC: fix `UnboundLocalError` on `voiced_ratio` (metric locals initialized at top of `qc_segment`). |
| `a8fa46a`  | QC: detect `tonal_artifact`, `low_voiced_content`, extreme-too-short (protect against non-speech / tones / EOS-attractor). |
| `b9852de`  | Final-gate: `too_long/too_short/monotone/long_pause` are soft quality flags, not hard rejections, when the composite score is high. Preserves good 30–40 s long-form segments that were previously being blocked. |

All 5 commits are pushed to `origin/arena/01a08d48-voice-ai-reference`.

## Registry state after fixes

Total voices: **50**
- CustomVoice built-in (no ref needed): **7** (ryan, aiden, dylan, uncle_fu, serena, vivian, sohee)
- Clone voices with valid, decodable reference (Base+VoiceClone, `allow_design=False`): **41**
  - EN male clone: 25 (includes the two must-test voices: `en_male_warm_storytelling_authoritative_02` and `en_male_warm_grounded_humanist_01`)
  - DE male clone: 10
  - DE female clone: 4
  - vd_e: 1 (locked to Golden Reference via `cache/voice_refs/VD-E.wav`)
- Explicitly disabled (no English female reference audio in this build): **2** (`en_female_calm_01`, `en_female_calm_02`). GUI greys these out and shows a clear error; no fallback.
- **BROKEN (ref-missing + clickable in GUI): 0**

### Reference-mapping decisions for legacy voices

Legacy cache/voice_refs WAVs never shipped in the repo; stale
`benchmark/male_deep_candidates/...` directories never existed.
Each was mapped to the closest auditioned MP3 actually present:

| voice_id                                          | new reference_path                                                  |
|---------------------------------------------------|---------------------------------------------------------------------|
| en_male_deep_01                                   | benchmark/fast_audition_round02/02_deep_warm_conversational.mp3    |
| en_male_deep_02                                   | benchmark/fast_audition_round02/01_ultra_deep_calm_resonant.mp3    |
| en_male_calm_deep_01                              | benchmark/fast_audition_round02/06_mature_documentary_natural.mp3  |
| en_male_warm_storytelling_authoritative_01        | benchmark/fast_audition/03_warm_storyteller.mp3                    |
| en_male_dark_documentary_01                       | benchmark/fast_audition_round02/03_dark_intellectual_investigative.mp3 |
| en_male_deep_warm_human_01                        | benchmark/fast_audition_round02/07_deep_clear_insightful.mp3       |
| en_male_ultra_calm_deep_01                        | benchmark/fast_audition_round02/01_ultra_deep_calm_resonant.mp3    |
| en_male_ultra_deep_calm_02                        | benchmark/fast_audition_round02/04_rich_velvet_baritone.mp3        |

All targets were probed with `ffprobe` and confirmed to have an audio
stream, duration > 0.5 s, and sample rate 24 kHz.

## Golden Reference

- `project/VD-E_GOLDEN_REFERENCE/VD-E.wav` — **unmodified**.
- SHA-256: `b156c02a60a873ad95fc92390c4a136c85308b20188373cd734bee5e5e5f2025` (matches production lock).
- Runtime cache `project/cache/voice_refs/VD-E.wav` is a byte-identical copy seeded so that `identity_lock._resolve_reference_path()` finds the locked reference at startup. `cache/voice_refs/` is git-ignored so this stays host-local.

## VoiceDesign model

NOT downloaded, NOT required for any GUI flow anymore. The only
code paths that still call `model_pool.get("voicedesign")` are:

1. `app/tts/voice_studio.design_reference()` — only reachable from
   `VoiceCloneEngine._ensure_prompt()` when `allow_design=True` AND
   `ref_path` is missing. With all GUI voices routed to existing refs,
   this is not reached during normal GUI operation.
2. `app/benchmark/phase2_ab.py`, `app/benchmark/phase3.py` —
   explicit Phase 2/3 benchmarking scripts, not invoked by GUI.
3. `app/ui/server.py` — only when a Phase-2 `engine_mode=voicedesign`
   config is passed, which the GUI does not produce.

## QC / retry / final-gate status

Preserved as required:

- **b9852de** — duration/prosody flags are advisory; clean voiced
  speech at 30–40 s routinely passes final-gate with scores 85–93
  (verified in Host Run 3 telemetry).
- **a8fa46a** — `tonal_artifact`, `low_voiced_content`,
  extreme-too-short remain hard-blocks (silence/tones/non-speech
  must be rejected).
- **80216f5** — `voiced_ratio` lifecycle fix; all QC paths define
  metric locals before use.
- Retry ladder (regeneration.py): seed/temperature/top_p/EOS all
  vary per attempt (seed offsets +7919 for attempt 2, +1299709 for
  attempt 3; silence_eos raises temperature + EOS penalty; prosody
  issues sweep temperature/top_p in both directions).

## What still needs to happen on a GPU host (STAGE 2–7)

The sandbox used to make these fixes has no torch / CUDA / model
weights, so generation testing has to run on the host machine
(which has torch 2.11.0+cu128, RTX 5060, and
`project/models/Qwen3-TTS-12Hz-1.7B-Base`).

A ready-to-run STAGE 2 smoke script is provided at the repo root:

```bash
cd project
python ../stage2_oneshot_smoke.py
```

It generates `cache/stage2/hello_<voice_id>.wav` for:
- `en_male_warm_storytelling_authoritative_02` (previously broken path)
- `en_male_warm_grounded_humanist_01` (known-good round02 winner)

It hard-pins `allow_design=False`, loads each ref, synthesizes
"Hello my friend." with the balanced sampler, and prints duration,
RMS, NaN check, PASS/FAIL.

**Staged validation plan (run in order, stop at first failure):**

1. ✅ STAGE 1 static audit — DONE (this report).
2. STAGE 2 one-shot "hello my friend" with `en_male_warm_storytelling_authoritative_02` via `stage2_oneshot_smoke.py`. Human-listen for intelligibility, correct male timbre, no tones/silence/noise.
3. STAGE 3 second voice `en_male_warm_grounded_humanist_01` via the same script. Compare against STAGE 2; if only one is bad, diagnose difference (reference/prompt/seed/sampler), don't loosen QC.
4. STAGE 4 slightly longer text (~1 sentence, 8–12 s) through the GUI, not the script — exercises the full GUI→runner→QC→final_gate path.
5. STAGE 5 short single-voice longform smoke (2–3 minutes / a handful of segments).
6. STAGE 6 full longform.
7. STAGE 7 TOP3 benchmark only if justified.

## Human listening checklist for STAGE 2/3

- [ ] Speech is clearly "Hello my friend." — intelligible English.
- [ ] Natural male human voice (not a tone, not a buzz, not noise, not another language).
- [ ] No clipped/garbled start or end.
- [ ] Duration roughly 1–3 s.
- [ ] RMS > ~0.01 (not near-silence).
- [ ] Same voice identity for repeat generations at the same seed.

## Root causes & fixes recap

| # | Symptom                                            | Root cause                                                                                  | Fix                                                                                                                          |
|---|----------------------------------------------------|---------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------|
| 1 | UnboundLocalError on voiced_ratio                  | Metric locals initialized after early-return path in qc_segment                             | Commit `80216f5` — move locals to top                                                                                        |
| 2 | QC false-positive rejects on good longform         | too_long/short/monotone/long_pause were catastrophic                                        | Commit `b9852de` — advisory flags + score-weighted final-gate                                                                |
| 3 | Tones / non-speech not caught                      | No explicit tonal_artifact / low_voiced_content detector                                    | Commit `a8fa46a` — add detectors, keep them as hard blocks                                                                   |
| 4 | GUI selections hit "VoiceDesign model not found"   | 8+10 clone voices had `reference_path` pointing at files not shipped with repo              | Commits `ee6a178` + `838db39` — point every GUI-exposed clone voice at an existing reference; mark two EN female voices unavailable |
| 5 | VD-E "GESPERRT" banner in German GUI               | `identity_lock` resolves runtime ref to `cache/voice_refs/VD-E.wav`, which was absent       | Seed cache from Golden Reference (byte-identical, cache is git-ignored, Golden untouched)                                   |
| 6 | Garbled/wrong-voice output                         | Consequence of #4: engine loaded with missing ref, allow_design=True, VoiceDesign model absent → corrupt prompt state | Fixed by #4 — engine always gets a real reference, `allow_design=False`, Base+VoiceClone path only                          |

## Files changed by the new commit (`838db39`)

```
project/voices/en_female_calm_01.json                     (available=false + note)
project/voices/en_female_calm_02.json                     (available=false + note)
project/voices/en_male_calm_deep_01.json                  (reference_path → existing round02 mp3)
project/voices/en_male_dark_documentary_01.json           (reference_path → existing round02 mp3)
project/voices/en_male_deep_01.json                       (reference_path → existing round02 mp3)
project/voices/en_male_deep_02.json                       (reference_path → existing round02 mp3)
project/voices/en_male_deep_warm_human_01.json            (reference_path → existing round02 mp3)
project/voices/en_male_ultra_calm_deep_01.json            (reference_path → existing round02 mp3)
project/voices/en_male_ultra_deep_calm_02.json            (reference_path → existing round02 mp3)
project/voices/en_male_warm_storytelling_authoritative_01.json  (reference_path → existing fast_audition mp3)
```

Local (not committed):
- `project/cache/voice_refs/VD-E.wav` (byte-identical copy of Golden).
- `stage2_oneshot_smoke.py` (host-run helper script; at repo root, not in project/ — add to .gitignore or delete after STAGE 2 if desired).

## Verdict

**NOT-YET-READY for full production longform** until STAGE 2 one-shot generation is run on the host and produces clean intelligible male-voice speech for both target voices. **Static/routing layer is production-ready** — no silent VoiceDesign fallback, no missing-ref crashes, no QC lifecycle bugs, Golden intact, GUI buttons for non-existent voices disabled. The remaining risk is generation quality, which cannot be evaluated in this sandbox and must be confirmed by running `stage2_oneshot_smoke.py` on a machine with the Base model + CUDA.
