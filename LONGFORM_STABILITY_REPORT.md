# Long-Form Stability & Production-GUI Integration — Report

Branch: `arena/01a08d48-voice-ai-reference`
Baseline: `8146e368a8aea11dd898dc6900b07341f0d7e767` (production ref_text plumbing)
Date: 2026-09-16
Golden VD-E.wav SHA (required, NOT modified):
`b156c02a60a873ad95fc92390c4a136c85308b20188373cd734bee5e5e5f2025`

## 1. Root-cause analysis of long-form instability

1. **Segmentation too short / no semantic boundaries.**
   The previous default was 420 / 120 / 700 chars (~28 / 8 / 47 s at 15 cps),
   and segments were always cut at `target_chars` without preferring
   sentence terminators. On long prose this produced many 25–35 s chunks
   that cut mid-thought, multiplied boundary artefacts, and made
   prosody jump 148 times for 483 s of audio.
2. **Final-QC gate too permissive for long-form.**
   `final_qc_gate(... min_score=min_score * 0.75)` accepted segments as
   low as ~58/100. In a 148-segment run that accumulates audible defects.
3. **No cross-segment continuity tracking.**
   Per-segment QC passed segments whose internal metrics looked fine but
   whose F0/LUFS/RMS drifted away from the running voice median.
4. **Hard clip/zero-pause concatenation** at segment boundaries: each
   segment was already edge-trimmed and fade-edged, but there was no
   cross-fade to suppress residual boundary clicks between
   independently synthesized chunks.
5. **GUI did not expose Production Clone voices as a distinct group**,
   so users ended up running CustomVoice speakers that were never tuned
   for long-form identity preservation. There was no visual separation
   between VD-E, built-in CustomVoices, and materialized clones.
6. **Default segmentation parameters used in production** were from
   an early short-script era, not the semantic long-form era.

None of these problems are in the VoiceClone reference contract; the
WAV + ref_text + seed contract from `8146e36` continues to be the
single correct pipeline, and is untouched.

## 2. Files changed

Core pipeline / segmentation / QC / assembly:
- `project/app/segmentation/__init__.py` — rewritten semantic segmenter
  (sentence/paragraph-aware, configurable presets, no word splits,
  cross-paragraph option).
- `project/app/project/pipeline.py` — new default segmentation
  (`balanced_60_90`), stricter final-gate ratio (default 0.88),
  inter-segment continuity tracker (`quality.continuity`), passes
  cross-fade option to assembler.
- `project/app/quality/qc.py` — tightened long-form penalties (silence
  ratio, voicing ratio, extreme speaking rate, short segments <50 %
  expected duration).
- `project/app/quality/continuity.py` (new) — rolling F0 / LUFS / RMS
  window; drift-scores candidate retries and logs continuity flags.
- `project/app/audio/assemble.py` — equal-power crossfade between
  adjacent segments (default 25 ms) with loudness-match preserved;
  pause insertion unchanged.

GUI:
- `project/app/gui/voice_view.py` — `voice_groups()` returning three
  groups: `locked` (VD-E), `custom`, `clone` (Production Clones).
- `project/app/gui/app.py` — voice card renders the three groups with
  clear headers; unavailable clones stay disabled and show
  "NICHT VERFÜGBAR – Referenz fehlt"; explanatory subtitle points at
  `cache/voice_refs/<id>.wav` as the canonical reference.

Tooling / benchmark:
- `project/tools/longform_benchmark.py` (new) — runs the real
  `Pipeline.process_file` across segmentation presets, collects
  diagnostics, writes WAVs + per-preset `summary.json` + master
  `benchmark.json`, and optionally runs faster-whisper/whisper ASR
  word-overlap if installed.
- `project/benchmark/longform/LISTENING_CHECKLIST.md` (new) — manual
  listening rubric per preset.

Production safety invariants preserved:
- Golden VD-E.wav NOT modified, `allow_design=False` default unchanged,
  MP3 references still hard-rejected in production,
  `VoiceCloneEngine(ref_text=entry.reference_text, reference_path=...)`
  is still the only clone path, no silent VoiceDesign/CustomVoice
  fallback, benchmark MP3s remain audition-only.

## 3. New segmentation design

`SegmentationConfig(target_chars, min_chars, max_chars, close_slack=0.45,
hard_start_min_chars=200, respect_paragraph_boundary=True)`

Algorithm:
1. Paragraphs → sentences via `text.analyze.split_sentences` (abbreviation,
   decimal, initials protection unchanged).
2. Sentences greedily appended, flushing when adding the next sentence
   would exceed `max_chars`, or when the buffer is past `target_chars`
   AND ends with a terminator (`.!?…`) AND is within `target*(1+close_slack)`
   (natural clause closer → clean break).
3. Single over-long sentences split at strong punctuation (;:…—–) →
   commas → word boundaries, never mid-word.
4. Post-processing merges tail/head fragments shorter than `min_chars`
   into neighbours when they fit in `max_chars`, eliminating
   micro-segments.
5. When `respect_paragraph_boundary=False` (xl_120_180 / adaptive_180)
   sentences flow across paragraphs up to the limits.

Named presets (scaled by chars_per_sec, 13.8 DE / 15.0 EN):
| preset | target | min | max |
|---|---|---|---|
| `short_30_45`    | ~37 s | ~20 s | ~50 s |
| `balanced_60_90` | ~60 s | ~30 s | ~95 s  (default production) |
| `long_90_120`    | ~95 s | ~45 s | ~130 s |
| `xl_120_180`     | ~135 s | ~70 s | ~185 s (cross-paragraph) |
| `adaptive_180`   | ~85 s | ~28 s | ~185 s (cross-paragraph) |

Advanced overrides via `cfg["advanced"]`:
`segment_target_chars`, `segment_min_chars`, `segment_max_chars`,
`segment_close_slack`, `segment_hard_start_min_chars`,
`segment_cross_paragraph`, `final_gate_ratio`, `qc_max_attempts`.

## 4. QC changes

- Silence-ratio threshold tightened: >0.65 hard-fails, >0.45 with short
  duration also fails (catches 0.16-s collapses and EOS drops).
- Extreme speaking rate (<50 % or >180 % expected duration) now applies
  an integrity penalty in addition to the pronunciation score.
- Voiced-content threshold tightened to <0.25 (instead of 0.35 and only
  for certain durations).
- Final gate threshold raised from 75 %·min_score to
  `final_gate_ratio`·min_score (default 88 % → ~68.6 floor). This is
  still best-of-N but refuses barely-audible garbage in long-form.
- New `quality.continuity.ContinuityState` tracks rolling median F0,
  LUFS, RMS over the last 6 accepted segments and logs a drift score +
  flags when a candidate drifts outside the envelope. It is used as a
  diagnostic signal in this change set (logged, seed-pinned by
  per-segment deterministic seeding); full ASR similarity is optional
  (see §5).
- Cross-fade (equal-power, 25 ms default) at assembly suppresses
  boundary clicks; pause logic unchanged.

## 5. Benchmark results

**Audio generation MUST be performed on the RTX 5060 host** — this
sandbox has no torch/CUDA/models. Run:

```powershell
# pre-flight
python project/tools/test_hardware_api.py

# (once) materialize if refs not yet present
python project/tools/materialize_references.py `
    --voice-id en_male_warm_storytelling_authoritative_02 --language English

# benchmark (5 presets, longform text, same voice)
python project/tools/longform_benchmark.py `
    --voice-id en_male_warm_storytelling_authoritative_02 `
    --text project/benchmark/longform_text_en.txt `
    --language English `
    --presets current,short_30_45,balanced_60_90,long_90_120,xl_120_180,adaptive_180
```

Output directory: `project/benchmark/longform/<voice_id>/<preset>/`
- `<preset>/<text>.wav` – master WAV (24 kHz per cfg; default 24 bit)
- `<preset>/summary.json` – segments, scores, retry count, duration,
  elapsed, LUFS/F0/RMS where captured, ASR similarity if whisper is
  installed, SHA256 prefix.
- `<preset>/benchmark.json` – master summary across presets.

After running, apply `LISTENING_CHECKLIST.md` to every preset WAV —
numerical scores alone cannot ship. Do NOT enable TOP3 / full long-form
until the winning preset scores ≥4 on Identity / Intelligibility /
Boundaries / Degradation for the multi-minute test.

## 6. GUI changes

- Voice card now has three labeled sections:
  1. **Gesperrte Produktionsstimme** — VD-E (unchanged, locked).
  2. **Custom Voices (eingebaute Qwen-Sprecher)** — Ryan/Aiden/Serena/…
  3. **Production Clone Voices (nach Materialisierung verfügbar)** —
     every `en_*`/`de_*` clone voice. Disabled (greyed, shows
     "NICHT VERFÜGBAR – Referenz fehlt") until
     `cache/voice_refs/<id>.wav` exists.
- Error dialog when generating on an unavailable clone voice shows the
  concrete materialization command and reason instead of the generic
  §13 message.
- No silent fallback to CustomVoice / VoiceDesign when a clone is
  selected: the build_engine path is unchanged and refuses with a
  clear error when the reference is missing.
- Startup benchmarking: no auto-run of a CustomVoice benchmark is
  triggered at GUI startup (no `start_batch`/`run_benchmark` calls in
  `gui/app.py` startup path — confirmed). `app/main.py --benchmark ...`
  remains an explicit CLI action.

## 7. VoiceDesign dependency status

- Base model (`Qwen3-TTS-12Hz-1.7B-Base`) is required for all TTS
  (CustomVoice AND production-clone inference).
- VoiceDesign (`Qwen3-TTS-12Hz-1.7B-VoiceDesign`) is required ONLY for
  the one-time materialization step (`tools/materialize_references.py`)
  to produce canonical reference WAVs. After materialization it is
  never loaded again for production inference (allow_design=False).
- When VoiceDesign is not installed:
  - Production clones with existing WAV references continue to work
    (Base-only path, VoiceDesign is never imported).
  - Production clones missing their WAV are disabled in the GUI with a
    clear "Referenz fehlt" message and the materialization command;
    they do not throw a model-not-found dialog at startup.
  - The materialization tool is the ONLY place that surfaces a clear
    "model not found" for VoiceDesign.
- Normal CustomVoice generation is not affected by VoiceDesign
  presence/absence.

## 8. Production safety confirmations

- Golden VD-E.wav: binary unchanged; runtime identity-lock
  (`assert_vd_e_usable`) and post-run `_verify_vd_e_hash_post_run` still
  active.
- No benchmark MP3 used as clone conditioning (still rejected by
  `_ensure_wav_reference` unless `VOICEOVER_REFS_ACCEPT_NONWAV=1`).
- No silent fallback from clone → VoiceDesign or clone → CustomVoice:
  `build_engine` raises when a reference is missing; `allow_design=False`
  remains the default on `VoiceCloneEngine`.
- Ref_text continues to come from `VoiceProfileEntry.reference_text`
  resolved via `resolve_reference_text()`; no hard-coded ref_text
  literals in runner/main/GUI/scripts.
- Exact SynthesisRequest signature used throughout
  (`text, language, speaker, instruct, sampling, seed,
  max_seconds_hint, speed`) — stage2/reproduce_voice/longform_benchmark
  all pass `speaker=` correctly.

## 9. Deliverables / commit

Commit on branch `arena/01a08d48-voice-ai-reference` will be printed
after push. Working tree clean before commit.

Final commit SHA:
Golden SHA: `b156c02a60a873ad95fc92390c4a136c85308b20188373cd734bee5e5e5f2025`
Benchmark output path: `project/benchmark/longform/<voice_id>/<preset>/*.wav`
Listening rubric: `project/benchmark/longform/LISTENING_CHECKLIST.md`

**Status:** CODE READY for host execution. Audio generation, ASR
similarity (if whisper installed), and manual listening remain MANDATORY
before any production-ready verdict. No premature "ship" based on
metrics.
