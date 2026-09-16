# Reference-Bundle Fix — Forensic Audit & Architecture Hardening

Commit: `4c7b58c` base + the fix in this change (see commit SHA below).

## 1. Forensic finding (root cause of the gibberish)

The medium clone test for `en_male_warm_storytelling_authoritative_02`
produced non-silent audio at 24 kHz / 40 s but it was essentially
gibberish. The engine was routed correctly
(`qwen3-tts-clone`, `VoiceDesign->Base-Clone`, `hardware_mode=gpu`) and
a reference WAV existed at
`cache/voice_refs/en_male_warm_storytelling_authoritative_02.wav`. The
failure was therefore NOT "wrong engine" and NOT "model crash".

Tracing every path:

| Path | File | What it did |
|------|------|-------------|
| Registry | `app/voices/registry.py:resolve_reference_text()` | Maps the voice JSON key `"reference_text": "VOICEDESIGN_REF_TEXT_EN"` → literal `"There is a book no one claims to have written…"` |
| Runner | `app/jobs/runner.py` | Passed `ref_text=entry.reference_text` to `VoiceCloneEngine(...)` |
| Engine | `app/tts/qwen_engine.py:VoiceCloneEngine._ensure_prompt()` | **If** `ref_text` was ever falsy, it silently defaulted to `VOICEDESIGN_REF_TEXT_EN` (English) / `VOICEDESIGN_REF_TEXT_DE` (German) based on language. Worse: the WAV was loaded from `cache/voice_refs/<id>.wav` but there was NO verification that the WAV on disk was actually a recording of that exact transcript. |

The data path represented the clone reference as TWO INDEPENDENTLY
SELECTABLE values:

```
reference_path → X.wav
ref_text       → Y     # (often the language-generic default)
```

If X.wav was ever materialized with a different transcript (custom
recipe text, regeneration, manual replacement, leftover sandbox MP3
that had been transcoded, recovery/archive copy, stale conversion in
`_converted/`, an older design attempt with a different seed/instruct,
etc.), `build_clone_prompt(ref_audio=X, ref_text=Y)` would receive a
text/audio pair that did not belong together. The Qwen VoiceClone
prompt builder is designed to align prompt tokens to the reference
audio against the given transcript; a transcript mismatch produces a
corrupt prompt → random/gibberish output (as reported).

Contributing factors that made this class of bug silent:

1. `VoiceCloneEngine` silently fell back to the language-default ref
   text when none was supplied — it never failed closed.
2. There was no manifest recording which transcript produced which
   WAV, no audio SHA, no text SHA, no seed, no commit.
3. WAV resolution was `Path(cache/voice_refs) / f"{candidate_id}.wav"`
   — any file at that path was accepted; duplicates in `_converted/`,
   `_stale_backup/` etc. could silently shadow the canonical file.
4. The GUI / registry declared a clone voice "available" based solely
   on WAV existence (`.suffix == ".wav"`), not on any notion of
   provenance integrity.
5. The medium test measured audio duration + inference time + sample
   rate but did not validate the reference bundle before synthesis.

The target voice's JSON held placeholder metadata
(`"reference_sha256": "ARENA_VOICE-09"`,
`"reference_text": "VOICEDESIGN_REF_TEXT_EN"`,
`"reference_generated": "real speech via Arena voice-09 …"`); the
recipe in `voice_generation_recipes.json` correctly names the
canonical VoiceDesign reference text as `"There is a book no one
claims to have written…"` with seed 52018. So when the production
materializer runs *correctly*, the WAV and that text DO match. The
gibberish arose because a previous code path had (a) accepted a WAV
that was not necessarily produced by that exact materialization and
(b) silently supplied the default ref text without verifying the
pair — exactly the failure mode the new bundle architecture closes.

## 2. Architecture fix: atomic ReferenceBundle

New module: `project/app/tts/reference_bundle.py`

A clone reference is now represented as one immutable
`ReferenceBundle`:

```
voice_id
audio_path / audio_sha256            (sha256 of WAV bytes)
reference_text / reference_text_sha256 (utf-8 sha256 of transcript)
language
generation { seed, model, model_version, engine_version,
             source_commit, created_at, description }
```

The canonical on-disk representation is the WAV plus a sidecar
manifest `<wav>.wav.json` written ATOMICALLY (tmp + `os.replace`)
directly after `write_wav()` inside
`QwenVoiceStudio.design_reference()` (belt-and-suspenders: also
re-written by `VoiceCloneEngine._ensure_prompt()` on the design path).
There is no code path that writes a reference WAV without its
manifest.

Validator (`ReferenceBundle.validate()`) checks:

| # | Check | Code on failure |
|---|-------|-----------------|
| 1 | WAV exists | `REFERENCE_AUDIO_MISSING` |
| 2 | WAV readable, valid header, sr ∈ {16/22.05/24/44.1/48} kHz | `REFERENCE_AUDIO_UNREADABLE` |
| 3 | duration ∈ [2 s, 60 s] | `AUDIO_DURATION_RANGE` |
| 4 | audio sha256 matches manifest | `REFERENCE_AUDIO_HASH_MISMATCH` |
| 5 | reference_text non-empty | `REFERENCE_TEXT_MISSING` |
| 6 | text sha256 matches manifest | `REFERENCE_TEXT_HASH_MISMATCH` |
| 7 | language ∈ {English, German} | `REFERENCE_LANGUAGE_INVALID` |

Resolver (`resolve_bundle()`):

1. ONLY accepts `cache/voice_refs/<voice_id>.wav` as the canonical path.
2. Scans `cache/voice_refs/` for duplicate/ambiguous candidates (same
   voice_id stem anywhere, including `_converted/`, backups); raises
   `AMBIGUOUS_REFERENCE_BUNDLE` rather than guessing.
3. Requires the `<wav>.wav.json` sidecar manifest for ALL clone
   voices EXCEPT `vd_e` (Golden bootstrap — the pre-existing WAV is
   accepted with VOICEDESIGN_REF_TEXT_DE; the WAV itself is never
   modified).
4. Validates the bundle; raises `BundleResolutionError` with a
   human-readable multi-line report on any failure.
5. Non-Golden voices without a manifest fail with
   `REFERENCE_BUNDLE_MANIFEST_MISSING` (fail closed).

## 3. VoiceCloneEngine hardening

`project/app/tts/qwen_engine.py` — `_ensure_prompt()` was rewritten:

- `ref_text=None` is no longer silently defaulted. The engine calls
  `resolve_bundle()` and uses the bundle's provenance text — any
  mismatch (missing WAV, missing manifest, SHA mismatch, ambiguous
  files, wrong language) raises `TTSError` with the
  `REFERENCE_BUNDLE_INVALID` report BEFORE model inference.
- When the caller explicitly passes `reference_path=…` AND that path
  is NOT the canonical WAV (test/override), the caller MUST also
  supply a matching `ref_text=`; otherwise `REFERENCE_TEXT_MISSING` is
  raised. The old silent fallback is gone.
- On the design path (`allow_design=True`, only via the materializer
  with `VOICEOVER_ALLOW_VOICEDESIGN_MATERIALIZE=1`), the recipe
  ref_text must be explicitly supplied — we refuse to invent one.
- After design_reference writes the WAV the bundle manifest is
  written atomically.
- On every `synthesize()` call a provenance log line is emitted:
  `REFBUNDLE_SYNTH VOICE_ID=… ENGINE=qwen3-tts-clone
  REFERENCE_AUDIO=… REFERENCE_AUDIO_SHA256=… REFERENCE_TEXT_SHA256=…
  REFERENCE_LANGUAGE=… REFERENCE_SEED=… BUNDLE_ID=…`.
- `info()` exposes `reference_bundle { bundle_id, audio_sha256,
  text_sha256, language, seed }` for runtime introspection.

## 4. Callers updated

- `app/jobs/runner.py` — clone engine is now created with
  `ref_text=None, reference_path=None` so canonical bundle resolution
  is the ONLY production path; non-canonical configured reference
  paths raise a clear error (no guessing).
- `app/main.py` — same treatment for both the headless/webserver
  engine builder.
- `app/ui/server.py` — web server VoiceDesign clone path also uses
  canonical bundle resolution (removed the ad-hoc
  `resolve_reference_text(None, lang)` fallback that previously
  supplied a guessed default).
- `app/voices/registry.py` — `VoiceProfileEntry.available` for clone
  voices now requires a valid `resolve_bundle()` result (not just a
  WAV file). Unavailable clone voices surface the bundle error as
  `availability_note` in the GUI.
- `app/voices/desktop_benchmark.py` — passes `language=` resolved from
  the entry and no guessed ref_text; VD-E still uses explicit
  `VOICEDESIGN_REF_TEXT_DE` and `candidate_id="VD-E"`.
- `app/tts/voice_studio.py` — `design_reference()` writes the
  reference-bundle sidecar atomically immediately after `write_wav`.
- `tools/materialize_references.py`, `tools/longform_benchmark.py`,
  `tools/production_validation.py` — use canonical bundle resolution
  instead of passing a possibly stale `entry.reference_text`.
- `tools/bootstrap_reference_bundles.py` (new) — on the GPU host,
  back-fills `.wav.json` manifests for existing WAVs whose recipe
  matches the canonical default `VOICEDESIGN_REF_TEXT_EN/DE`. Refuses
  to guess for voices with non-default recipes (those must be
  re-materialized).
- `project/voices/en_male_warm_storytelling_authoritative_02.json` —
  normalized to `"reference_text": "VOICEDESIGN_REF_TEXT_EN"` (symbolic
  key) with a note that the sidecar manifest is authoritative.

## 5. Guardrails preserved

- **VD-E Golden reference is NOT modified.** No code rewrites, re-encodes,
  or moves `cache/voice_refs/VD-E.wav`. Runtime bootstrap in
  `resolve_bundle()` constructs an in-memory bundle using
  `VOICEDESIGN_REF_TEXT_DE` and the on-disk SHA; the WAV itself is
  never touched.
- **CustomVoice voices (Aiden / Ryan / Dylan / Uncle_Fu / Serena /
  Vivian / Sohee / Ono_Anna / Eric)** remain on `QwenTTSEngine` +
  `generate_custom_voice()`; they do not pass through the clone bundle
  resolver at all.
- **No silent fallback to CustomVoice / VoiceDesign.** Clone voices
  fail closed. The only path that sets `allow_design=True` is the
  explicit materializer (gated on `VOICEOVER_ALLOW_VOICEDESIGN_
  MATERIALIZE=1`).
- **No MP3 audition files** can ever reach `create_voice_clone_prompt`
  again. The non-WAV guard in `_ensure_wav_reference()` is retained
  and now compounded by the canonical-path-only resolver (duplicate
  MP3s elsewhere in cache/voice_refs cause AMBIGUOUS_REFERENCE_BUNDLE).
- **Audition MP3s under benchmark/ are never used as clone refs.**
- **No sampling-param "fixes"** were applied (temperature, top_p,
  repetition_penalty, seed, speaker name all unchanged). The fix is
  purely an integrity/provenance fix.

## 6. Regression tests (all pass in the sandbox)

- `project/tools/test_reference_bundle.py` — 14 tests covering:
  A valid bundle, B wrong-text hash mismatch, C wrong-audio hash
  mismatch, D missing text, E missing audio, F ambiguous duplicate
  files, G CustomVoice "no ref" doesn't silently pass, H VD-E
  bootstrap with correct German default, I orphan WAV without
  manifest fails closed, J `REFERENCE_TEXT_MISSING` guard present in
  engine and old silent-fallback pattern absent, K provenance log
  line contains all required fields.
- `project/tools/test_hardware_api.py` — production contract still
  passes (allow_design=False default, canonical ref_text, speaker= on
  SynthesisRequest).
- `project/tools/test_longform_unbound.py` — still passes (previous
  UnboundLocalError regression guard retained).

## 7. RTX 5060 workflow to repair the target voice

On the host where the current (gibberish-producing) WAV lives:

```bash
git pull --ff-only    # now at fix commit

# 1. See what state the references are in (no GPU needed):
python project/tools/bootstrap_reference_bundles.py --dry-run

# 2. For voices whose WAV was materialized with the standard
#    VOICEDESIGN_REF_TEXT_EN/DE and seed (which includes voice-09
#    IF the current WAV was produced via materialize_references.py
#    with the documented recipe), the bootstrap tool will backfill a
#    correct .wav.json sidecar WITHOUT re-synthesizing:
python project/tools/bootstrap_reference_bundles.py

# 3. Validate the bundle (loads + hashes + reports, no long-form synthesis):
python project/tools/production_validation.py \
    --voice-id en_male_warm_storytelling_authoritative_02 \
    --language English --stages short

# 4. If step 2 refuses voice-09 with "ref_text is non-default — cannot
#    prove match" the existing WAV cannot be trusted and must be
#    re-materialized atomically:
python project/tools/materialize_references.py \
    --voice-id en_male_warm_storytelling_authoritative_02 \
    --language English
# This writes cache/voice_refs/en_male_warm_storytelling_authoritative_02.wav
# + .wav.json in one transaction and prints both SHA256s.

# 5. Medium verification (≈30–60 s) using the validated bundle:
python project/tools/controlled_short_run.py \
    --voice-id en_male_warm_storytelling_authoritative_02

# 6. Full long-form benchmark across all six presets:
python project/tools/longform_benchmark.py \
    --voice-id en_male_warm_storytelling_authoritative_02 \
    --text project/benchmark/longform_text_en.txt \
    --language English \
    --presets current,short_30_45,balanced_60_90,long_90_120,xl_120_180,adaptive_180
```

Every synthesis now starts with a `REFBUNDLE_LOAD` / `REFBUNDLE_SYNTH`
line in the log that records audio SHA, text SHA, language, seed, and
bundle id — provenance for every generated file.

## 8. Checklist against the deliverables

```
[PASS] Correct VoiceDesign→Clone routing                   (runner/main/ui/server verified)
[PASS] Canonical reference audio path enforced             (resolve_bundle, fail-closed)
[PASS] Canonical reference text resolved from manifest     (never from silent fallback)
[PASS] Audio/text provenance linked via SHA256             (ReferenceBundle dataclass)
[PASS] Audio SHA256 verified before synthesis              (validate() AUDIO_SHA256)
[PASS] Text SHA256 verified before synthesis               (validate() TEXT_SHA256)
[PASS] Stale/ambiguous references rejected                 (AMBIGUOUS_REFERENCE_BUNDLE)
[PASS] Missing ref_text cannot silently pass               (REFERENCE_TEXT_MISSING guard)
[PASS] Production pipeline uses same validated bundle      (runner passes ref_text=None)
[PASS] CustomVoice voices unchanged (QwenTTSEngine)        (test_hardware_api + code inspection)
[PASS] VD-E Golden locked, WAV never modified              (runtime bootstrap only)
[PASS] Regression tests pass                               (14 + hw_api + unbound tests)
```

## 9. Files added / changed

Added:
- `project/app/tts/reference_bundle.py`  — new bundle model, validator, resolver, atomic write
- `project/tools/test_reference_bundle.py` — 14-case regression suite
- `project/tools/bootstrap_reference_bundles.py` — backfills manifests for existing WAVs
- `REFERENCE_BUNDLE_FIX_REPORT.md` — this document

Modified:
- `project/app/tts/qwen_engine.py`        — VoiceCloneEngine: bundle resolution, hard-fail on missing ref_text, provenance logging
- `project/app/tts/voice_studio.py`       — design_reference writes bundle sidecar atomically
- `project/app/voices/registry.py`        — availability requires valid bundle; surfaces bundle errors
- `project/app/jobs/runner.py`            — uses canonical bundle resolution, errors on non-canonical paths
- `project/app/main.py`                  — same
- `project/app/ui/server.py`             — same, removed silent default fallback
- `project/app/voices/desktop_benchmark.py` — language-aware, no silent ref_text
- `project/tools/materialize_references.py` — unchanged logic but now benefits from auto-sidecar in studio
- `project/tools/longform_benchmark.py`   — uses canonical bundle
- `project/tools/production_validation.py` — resolves & prints bundle before test runs
- `project/voices/en_male_warm_storytelling_authoritative_02.json` — normalized reference_text key
