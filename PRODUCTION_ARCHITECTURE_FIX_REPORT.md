# Production-Architecture Fix — Final Report

Branch: `arena/01a08d48-voice-ai-reference`
Date: 2026-09-15
Golden Reference SHA: `b156c02a60a873ad95fc92390c4a136c85308b20188373cd734bee5e5e5f2025` (byte-identical, untouched).

---

## 1. Root cause

Two defects conspired to produce "VoiceDesign model not found" and
"garbled / wrong voice" from the GUI:

1. **Silent VoiceDesign fallback in the engine builder.**
   `app/jobs/runner.py` and `app/main.py` defaulted `allow_design=True`
   whenever a configured reference was missing. With the VoiceDesign
   model not installed on the sandbox/host path in question, that
   branch raised `model-not-found` *or* — worse — drove partially
   initialized state into `build_clone_prompt` when a bad reference
   existed.

2. **Misuse of audition MP3s as clone-conditioning references.**
   Commit `838db39` (and parts of `ee6a178`) pointed `reference_path`
   at files under `benchmark/fast_audition*/*.mp3`. Those MP3s are
   **audition renders** — final outputs made for human listening —
   *not* production clone references.
   - The MP3s were produced by Arena TTS and speak the **audition**
     text ("Every discovery begins with a question…" / "Jede Entdeckung
     beginnt mit einer Frage…").
   - `QwenVoiceStudio.build_clone_prompt` is called with
     `VOICEDESIGN_REF_TEXT_EN/DE` ("There is a book no one claims to
     have written…" / "Es gibt ein Buch…").
   - Passing the audition MP3 as `ref_audio` while `ref_text` says a
     different sentence causes a **text/audio mismatch** → corrupt
     clone prompt → garbled / tonal / wrong-voice output. The engine
     even auto-transcoded the MP3 to 24 kHz WAV, hiding the mistake.

## 2. Why 838db39 was insufficient (and architecturally wrong)

It *did* make every `reference_path` point at an existing file, which
stopped the `FileNotFoundError`, but:

- It substituted **audition renders** for **production references**.
- It silently allowed `allow_design=False` to be set on the basis of a
  file whose *content* (speech text, generation pipeline, provenance,
  format) did not match what `build_clone_prompt` expects.
- It masked the real architectural fact: **no EN/DE clone voice except
  VD-E has its production reference WAV materialized in a fresh
  checkout.** The correct reaction is "mark unavailable / give the
  user a clear materialization path", not "plug in any audio file".

## 3. Benchmark vs. production-reference distinction

| Aspect | Audition / Benchmark MP3 | Production clone reference WAV |
|---|---|---|
| Location | `benchmark/fast_audition*/`, `benchmark/german_*_audition/` | `cache/voice_refs/{candidate_id}.wav` |
| Source | Arena TTS (sandbox placeholder) | Qwen3-TTS-12Hz-1.7B-VoiceDesign via `design_reference()` on RTX 5060 |
| Spoken text | Audition script ("Every discovery…" / "Jede Entdeckung…") | `VOICEDESIGN_REF_TEXT_EN/DE` ("There is a book…" / "Es gibt ein Buch…") |
| Purpose | Human listening / audition | Conditioning input to `create_voice_clone_prompt(ref_audio, ref_text)` on the Base model |
| Format | MP3 (final render) | 24 kHz mono 16-bit PCM WAV |
| `provenance` (recipes) | `arena_placeholder` | `actual_qwen` (only VD-E today) |
| Safe to use as `ref_audio` in build_clone_prompt? | **NO** (text/audio mismatch → corrupt prompt) | **YES** (ref_text matches spoken text, same pipeline) |

## 4. Fixes applied

### 4.1 Voice JSONs point to the canonical production path

All 42 clone voices (other than VD-E) now have
`reference_path = "cache/voice_refs/{voice_id}.wav"` and
`provider="qwen3-tts"`, `model="Qwen3-TTS-12Hz-1.7B-Base (VoiceDesign->Clone)"`.
No JSON points at `benchmark/*.mp3` or at the non-existent
`benchmark/male_deep_candidates/.../part1.mp3` anymore.

### 4.2 Silent VoiceDesign fallback removed

`app/jobs/runner.py` and `app/main.py` now default `allow_design=False`
for all clone voices. When a reference is missing and
`VOICEOVER_ALLOW_VOICEDESIGN_MATERIALIZE` is not set (default), the
engine builder raises a clear `RuntimeError` naming the missing WAV
and the exact command to materialize it, instead of silently calling
`model_pool.get("voicedesign")`. The GUI catches this and surfaces it.

### 4.3 Registry computes availability honestly

`VoiceRegistry.entries()` now marks a clone voice as `available=True`
**only when** its canonical `cache/voice_refs/{id}.wav` exists and is
a WAV. Missing-reference voices are returned with `available=False`
plus a German-language note pointing at
`tools/materialize_references.py`. The GUI already disables the radio
button for `available=False` voices and shows an error on select, so
users can't launch a job that will auto-voiceDesign.

### 4.4 Non-WAV references hard-rejected

`VoiceCloneEngine._ensure_wav_reference()` now refuses MP3/M4A/OGG/FLAC
inputs in production (only allowed if `VOICEOVER_REFS_ACCEPT_NONWAV=1`
is explicitly set for testing). The error message explains the
text/audio-mismatch risk and points at the materialization tool. The
old transcode path is preserved under that opt-in flag for
debugging/testing. (Also fixed a latent bug: the function was
importing `TTSError` from a non-existent `..errors` module.)

### 4.5 Explicit materialization tool (new)

`project/tools/materialize_references.py` is the *only* sanctioned way
to populate `cache/voice_refs/`:

- `--list-missing` shows every voice that needs its production
  reference materialized (no GPU required).
- `--voice-id <id> --language <lang>` materializes one voice by
  calling `QwenVoiceStudio.design_reference(candidate_id, description,
  language, ref_text=VOICEDESIGN_REF_TEXT_<LANG>, seed=<recipe-seed>)`,
  which uses the VoiceDesign model exactly once to produce
  `cache/voice_refs/{id}.wav` (24 kHz mono 16-bit PCM, correct text).
- `--all-missing` materializes every missing production candidate.
- `--dry-run` prints the plan without loading models.
- Sets `VOICEOVER_ALLOW_VOICEDESIGN_MATERIALIZE=1` in its own process
  only, so normal GUI/runtime paths still default to `allow_design=False`.

This explicitly requires the VoiceDesign model (as the architecture
dictates) rather than downloading it silently or papering over the
missing reference with a substitute audio file.

### 4.6 VD-E locked path preserved

- `project/VD-E_GOLDEN_REFERENCE/VD-E.wav` is untouched;
  SHA-256 = `b156c02a60a873ad95fc92390c4a136c85308b20188373cd734bee5e5e5f2025`.
- Runtime `cache/voice_refs/VD-E.wav` is the byte-identical seeded
  copy used by `identity_lock` (cache is git-ignored, host-local).
- VD-E path still uses `allow_design=False` (no redesign).

## 5. Reference lifecycle (now correct)

```
GUI voice selection
  → VoiceRegistry.entries()
      ├─ backend=customvoice → CustomVoice engine (no ref needed)
      └─ backend=clone
          ├─ cache/voice_refs/{id}.wav EXISTS
          │     → available=True
          │     → runner builds VoiceCloneEngine(allow_design=False, reference_path=<wav>)
          │     → _ensure_prompt: ref is WAV → VoiceRef(ref_text=VOICEDESIGN_REF_TEXT_*)
          │     → build_clone_prompt(ref_audio=<wav>, ref_text=<correct matching text>)
          │     → synth_clone on Base model
          │     → QC/retries/final-gate (existing behavior preserved)
          └─ cache/voice_refs/{id}.wav MISSING
                → available=False (GUI radio button disabled; select gives clear error)
                → Job start raises RuntimeError pointing at materialize tool
                → NO silent VoiceDesign, NO benchmark-MP3 substitution
```

Materialization (explicit, host-side, requires VoiceDesign model):
```
python project/tools/materialize_references.py --voice-id <id> --language English
  → sets VOICEOVER_ALLOW_VOICEDESIGN_MATERIALIZE=1
  → QwenVoiceStudio.design_reference(id, description, language, ref_text, seed)
      → pool.get("voicedesign")
      → model.generate_voice_design(text=ref_text, language=language, instruct=description)
      → write_wav(cache/voice_refs/{id}.wav, wav, sr, 16)
  → restart GUI; voice is now available; Base+VoiceClone path runs allow_design=False
```

## 6. Per-voice provenance

- **vd_e** — `actual_qwen`, locked golden. Reference:
  `cache/voice_refs/VD-E.wav` (runtime) ≡
  `project/VD-E_GOLDEN_REFERENCE/VD-E.wav`, SHA
  `B156C02A…F2025`, WAV 24 kHz mono 16-bit, spoken text =
  `VOICEDESIGN_REF_TEXT_DE` ("Es gibt ein Buch…"), allow_design=False,
  model = Base. Ready.
- **en_male_warm_storytelling_authoritative_02** — Locked human
  favorite (voice-09, position 4), recipe seed 52018, description
  "warm storytelling authoritative – superior version of current
  favorite, deep warm authority clarity", provenance `arena_placeholder`,
  canonical reference = `cache/voice_refs/en_male_warm_storytelling_authoritative_02.wav`
  **NOT yet materialized** in this checkout. The file at
  `benchmark/fast_audition/04_warm_storytelling_authoritative_02.mp3`
  is the **audition render** (Arena TTS, "Every discovery begins…"),
  not the clone-conditioning reference — must not be used for
  conditioning. Materialize on RTX 5060 via the tool.
- **en_male_warm_grounded_humanist_01** — Saved human shortlist
  (voice-25), recipe seed 52034, description "warm grounded humanist
  – empathetic, sincere, mature, comforting and human", provenance
  `arena_placeholder`, canonical reference =
  `cache/voice_refs/en_male_warm_grounded_humanist_01.wav` **NOT yet
  materialized**. `benchmark/fast_audition_round02/08_warm_grounded_humanist.mp3`
  is the audition render only.
- **All other en/de clone voices (40 total)** — Same pattern: recipes
  carry seed, description, and `voicedesign_reference_text`; canonical
  reference is `cache/voice_refs/{id}.wav`; all are `arena_placeholder`
  except VD-E; none are materialized in a fresh checkout.
- **7 CustomVoice built-ins** (ryan/aiden/dylan/uncle_fu/serena/vivian/sohee)
  — no reference needed, built into the CustomVoice model, always
  available.

## 7. Reference-text / audio consistency after fix

For every available clone voice after materialization:
- `ref_audio` speaks **exactly** `VOICEDESIGN_REF_TEXT_EN/DE` (because
  `design_reference` generates the WAV from that exact text).
- `build_clone_prompt` is called with that same `ref_text`.
- No text/audio mismatch, no corrupt-prompt path.

## 8. Model routing

| Voice type | `allow_design` | Model(s) loaded |
|---|---|---|
| CustomVoice (built-ins) | n/a | `Qwen3-TTS-12Hz-1.7B-CustomVoice` only |
| Clone, ref exists (incl. VD-E) | `False` | `Qwen3-TTS-12Hz-1.7B-Base` only |
| Clone, ref missing (GUI) | n/a | Error — job aborts, voice disabled |
| Clone, ref missing (materialize tool) | `True` (only in that process) | `VoiceDesign` once to write WAV; then `Base` for clone prompt (synth in subsequent runs) |

The VoiceDesign model is therefore **genuinely required** exactly once
per clone voice to materialize its reference WAV. After that, Base +
VoiceClone runs forever with `allow_design=False`. This matches the
documented pipeline in `VOICE_GENERATION_ARCHITECTURE.md §B/C/D/G`.

## 9. Files modified

```
project/app/jobs/runner.py                # remove silent allow_design=True; clear RuntimeError on missing ref
project/app/main.py                       # same fix
project/app/voices/registry.py            # compute availability from real ref existence; WAV check
project/app/tts/qwen_engine.py            # reject non-WAV refs in production; fix TTSError import
project/voices/*.json   (36 files)        # canonical reference_path = cache/voice_refs/{id}.wav
                                          # + provider/model reset to qwen3-tts / Base (VoiceDesign->Clone)
project/tools/materialize_references.py   # NEW: sanctioned one-shot reference materialization tool
stage2_oneshot.py                         # NEW: correct STAGE 2 one-shot smoke script (replaces the old buggy one)
PRODUCTION_ARCHITECTURE_FIX_REPORT.md     # this report
```

Reverted/superseded:
- Reference-path changes from commits `ee6a178` and `838db39` that
  pointed voices at `benchmark/*.mp3` are replaced by canonical
  `cache/voice_refs/*.wav` paths.

## 10. Host-run procedure to bring EN voices online (RTX 5060)

On the host machine that has torch+CUDA and **all three** Qwen models
(Base / CustomVoice / **VoiceDesign**) under `MODELS_DIR`:

```bash
# 1) Materialize the two must-test EN voices:
python project/tools/materialize_references.py \
    --voice-id en_male_warm_storytelling_authoritative_02 \
    --language English
python project/tools/materialize_references.py \
    --voice-id en_male_warm_grounded_humanist_01 \
    --language English

# 2) One-shot smoke (hard-pins allow_design=False, refuses MP3, prints full diagnostics):
python stage2_oneshot.py
# Produces project/cache/stage2/hello_<voice_id>.wav

# 3) HUMAN LISTENING (mandatory — acoustic QC alone is insufficient):
#    - Is it clearly "Hello my friend." in natural male English?
#    - Correct vocal identity (warm storytelling authoritative / warm grounded humanist)?
#    - No tones/buzz/silence/noise/garble/clipping/non-English?
#    - Duration ~1–3 s?
#    - Stable across a second run with the same seed?

# 4) Only after (3) passes:
#    - STAGE 4: slightly longer text via the GUI
#    - STAGE 5: short single-voice longform
#    - STAGE 6: full longform
#    - STAGE 7: TOP3 / premium batch if justified
```

The `stage2_oneshot.py` script prints for each voice: reference file
path, SHA256, sr/ch/bit-depth/duration, backend_mode, language,
allow_design (hard-pinned False), selected model, ref_text,
clone-prompt construction, synth time, output path, output
sr/ch/duration/RMS/NaN, and an automatic PASS/FAIL — but the decisive
verdict remains human listening.

## 11. Current verdict: NOT YET READY for production generation

- Architecture is now **correct and honest**:
  - No silent VoiceDesign fallback.
  - No benchmark MP3 used as clone-conditioning.
  - Missing production references disable the voice in the GUI and
    produce an explicit error pointing to the materialization tool.
  - Clone-prompt creation always pairs a WAV with its matching ref_text.
  - VD-E locked, Golden SHA intact.
- Generation testing (STAGE 2–7) **cannot** run in this sandbox (no
  torch, no CUDA, no Qwen models). It must run on the RTX 5060 host
  after materializing the two EN production references with
  `materialize_references.py` (which requires the VoiceDesign model
  for that initial step — by design, per the documented pipeline).
- Real "hello my friend" outputs + human listening are required before
  any voice can be marked READY.
