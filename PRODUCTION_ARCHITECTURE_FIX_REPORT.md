# Production-Architecture Fix — Final Report

Branch: `arena/01a08d48-voice-ai-reference`
Final commit: `743809b` (on top of `d986d2b` architecture fix)
Date: 2026-09-15
Golden Reference SHA: `b156c02a60a873ad95fc92390c4a136c85308b20188373cd734bee5e5e5f2025` (byte-identical, untouched).

---

## 1. Root cause

Two layers of defects:

**A. Architectural (fixed in `d986d2b`):**
- Audition-MP3s (`benchmark/fast_audition*/*.mp3`) were silently used as
  clone-conditioning references. They are final renders speaking the
  audition script ("Every discovery begins…"), while `build_clone_prompt`
  pairs them with `VOICEDESIGN_REF_TEXT_EN/DE` ("There is a book…") →
  text/audio mismatch → corrupt clone prompt → garbled/tonal/wrong-voice
  output.
- `runner.py`/`main.py` defaulted `allow_design=True` on missing refs →
  silently hit VoiceDesign model (not installed) → "model not found"
  and partial-state corruption.

**B. Tooling API mismatch (fixed in `743809b`, this commit):**
`HardwareInfo` (project/app/hardware/detector.py) exposes `mode`
(`"gpu"|"gpu_conservative"|"cpu"`), `gpu_name`, `cuda_available`,
`device_capability`, etc. and `recommend_torch_dtype(hw)` returns the
torch dtype string. It does **NOT** expose `.device` or `.dtype`. The
two new scripts (`tools/materialize_references.py` and
`stage2_oneshot.py`) accessed `hw.device` / `hw.dtype`, causing
`AttributeError` on the RTX 5060 host before any model load.

Why 838db39 was insufficient: it substituted audition MP3s for
production references purely because they existed, without checking
provenance or ref_text/audio pairing. It stopped the FileNotFoundError
but produced corrupt-prompt synthesis.

## 2. Benchmark vs. production-reference distinction

| Aspect | Audition / Benchmark MP3 | Production clone reference WAV |
|---|---|---|
| Location | `benchmark/fast_audition*/`, `benchmark/german_*_audition/` | `cache/voice_refs/{candidate_id}.wav` |
| Source | Arena TTS (sandbox placeholder) | Qwen3-TTS-12Hz-1.7B-VoiceDesign via `design_reference()` on RTX 5060 |
| Spoken text | Audition script ("Every discovery…" / "Jede Entdeckung…") | `VOICEDESIGN_REF_TEXT_EN/DE` ("There is a book…" / "Es gibt ein Buch…") |
| Purpose | Human listening / audition | Conditioning input to `create_voice_clone_prompt(ref_audio, ref_text)` on Base |
| Format | MP3 320k final render | 24 kHz mono 16-bit PCM WAV |
| Provenance (recipes) | `arena_placeholder` | `actual_qwen` (only VD-E today) |
| Safe as `ref_audio` in `build_clone_prompt`? | **NO** (text/audio mismatch → corrupt prompt) | **YES** |

## 3. Fixes

### Architecture (`d986d2b`)
- 42 clone voices' `reference_path` reset to canonical
  `cache/voice_refs/{id}.wav`; provider/model reset to `qwen3-tts` /
  `Qwen3-TTS-12Hz-1.7B-Base (VoiceDesign->Clone)`.
- `runner.py`/`main.py` default `allow_design=False`; missing refs raise
  a clear RuntimeError pointing at the materialize tool.
- `registry.py` marks voices available only when their canonical WAV
  exists; GUI disables them otherwise.
- `qwen_engine._ensure_wav_reference` hard-rejects non-WAV refs with
  an explanatory TTSError (opt-in via `VOICEOVER_REFS_ACCEPT_NONWAV=1`
  only for explicit tests). Fixed stale `from ..errors import TTSError`
  to use `from .engine_base import TTSError`.
- New tool `project/tools/materialize_references.py` — the ONLY
  sanctioned path to populate `cache/voice_refs/`. Requires the
  VoiceDesign model exactly once per voice, sets
  `VOICEOVER_ALLOW_VOICEDESIGN_MATERIALIZE=1` only in its own process,
  uses recipe seed + correct `VOICEDESIGN_REF_TEXT_*`, writes 24 kHz
  mono 16-bit WAV.
- New script `stage2_oneshot.py` replaces the buggy earlier version:
  hard-pins `allow_design=False`, refuses MP3s, prints full
  diagnostics.
- VD-E locked: SHA `b156c02a…f2025` unchanged; runtime cache copy
  byte-identical; `allow_design=False` preserved.

### Tooling / HardwareInfo (`743809b`)
- `materialize_references.py` and `stage2_oneshot.py` now use
  `hw.mode` + `recommend_torch_dtype(hw)` + `hw.gpu_name` instead of
  non-existent `hw.device`/`hw.dtype`.
- `materialize_references.py` auto-detects a neighboring
  `VoiceOverApp-AgentReady-Latest/project/models` install and sets
  `VOICEOVER_MODELS_DIR`, so fresh clones can resolve models without
  manual env configuration.
- `stage2_oneshot.py` resolves `project/` robustly when invoked from
  either the repo root or project dir; auto-detects models dir same way.
- New non-GPU smoke test `project/tools/test_hardware_api.py`:
  parses both scripts' ASTs to forbid `hw.device`/`hw.dtype` accesses
  and verifies the `HardwareInfo` + `recommend_torch_dtype` contract.

### Files modified/added
```
project/app/jobs/runner.py                  allow_design=False default; clear error on missing ref
project/app/main.py                        same fix
project/app/voices/registry.py             availability computed from WAV existence
project/app/tts/qwen_engine.py             non-WAV refs rejected; TTSError import fixed
project/voices/*.json                      reference_path -> cache/voice_refs/{id}.wav (36 files)
project/tools/materialize_references.py    NEW: sanctioned reference materialization tool
project/tools/test_hardware_api.py         NEW: non-GPU smoke test for HardwareInfo API
stage2_oneshot.py                          NEW: STAGE 2 one-shot smoke script
```

## 4. Canonical reference status for every production voice

- **CustomVoice (7):** built-in, no ref needed (ryan/aiden/dylan/uncle_fu/serena/vivian/sohee).
- **vd_e:** `cache/voice_refs/VD-E.wav`, sha256 `B156C02A…F2025`, WAV,
  `actual_qwen`, locked, `allow_design=False`. Ready.
- **42 clone voices (en/de male + female):** canonical reference
  `cache/voice_refs/{id}.wav` NOT materialized in a fresh checkout
  (expected — generation of the WAV requires `Qwen3-TTS-12Hz-1.7B-VoiceDesign`
  on RTX 5060 exactly once per voice, per §B/G of the architecture doc).
  Voices are marked `available=False` in GUI until materialized.

Target-voice recipes (from `voice_generation_recipes.json`):
- `en_male_warm_storytelling_authoritative_02` — seed 52018, description
  "warm storytelling authoritative – superior version of current
  favorite, deep warm authority clarity", ref_text =
  VOICEDESIGN_REF_TEXT_EN, provenance `arena_placeholder` (audition MP3
  at `benchmark/fast_audition/04_warm_storytelling_authoritative_02.mp3`
  is audition render only).
- `en_male_warm_grounded_humanist_01` — seed 52034, description
  "warm grounded humanist – empathetic, sincere, mature, comforting
  and human", ref_text = VOICEDESIGN_REF_TEXT_EN, provenance
  `arena_placeholder` (audition MP3 at
  `benchmark/fast_audition_round02/08_warm_grounded_humanist.mp3`).

The audition MP3s in `benchmark/` must stay exactly as they are
(30-something KB, 15 s of real speech at 24 kHz, SHA prefixed
`ARENA_VOICE-xx`). They are not production references.

## 5. Model routing after fix

| Scenario | `allow_design` | Models loaded |
|---|---|---|
| CustomVoice built-ins | n/a | CustomVoice only |
| Clone, ref WAV exists (incl. VD-E) | **False** | Base only |
| Clone, ref missing, normal GUI/job | n/a | Error raised, voice disabled — **no** model load |
| Clone, ref missing, `materialize_references.py` | True (in that process only) | VoiceDesign once → writes WAV (subsequent runs use Base) |

VoiceDesign model is genuinely required exactly once per clone voice
to materialize the WAV reference. This matches the documented pipeline;
it is **not** downloaded silently — the tool must be invoked
explicitly by the user.

## 6. Reference-text / audio consistency

After materialization via `design_reference`, the WAV at
`cache/voice_refs/{id}.wav` is generated from `VOICEDESIGN_REF_TEXT_EN/DE`
with the recipe seed + description, then stored. `build_clone_prompt`
is called with that same `ref_text`, so text and audio always match —
no corrupt-prompt path remains.

## 7. Host-run procedure (RTX 5060, CUDA 12.8, torch 2.11.0+cu128)

From the repo root:
```powershell
# 0) Sanity (non-GPU, passes offline)
python project/tools/test_hardware_api.py

# 1) Materialize the two target references
python project/tools/materialize_references.py --voice-id en_male_warm_storytelling_authoritative_02 --language English
python project/tools/materialize_references.py --voice-id en_male_warm_grounded_humanist_01 --language English

# 2) Verify WAVs (script prints sha/sr/ch/duration)
#    Expected: WAV, 24 kHz mono, 16-bit PCM, ~5-15s speaking VOICEDESIGN_REF_TEXT_EN
#              SHA printed, NaN-free.

# 3) One-shot "Hello my friend." (allow_design=False, Base+VoiceClone, no MP3 fallback)
python stage2_oneshot.py
# Writes project/cache/stage2/hello_<voice_id>.wav and prints:
#   voice_id / canonical ref / sha256 / sr/ch/bd/dur / language / model / allow_design
#   / ref_text / prompt-build status / synth time / output dur/RMS/peak/NaN/PASS.
```

**Acoustic PASS from the script is necessary but not sufficient.**
Both output WAVs require human listening for intelligibility, natural
timbre, correct voice identity, and absence of tones/silence/noise
before the voice can be marked production-ready.

After human validation of both one-shots, continue per the staged
plan: STAGE 4 (GUI multi-sentence) → STAGE 5 (short longform) →
STAGE 6 (full longform) → STAGE 7 (TOP3).

## 8. Current status

- Code changes: complete and pushed (commits `80216f5`, `b9852de`,
  `a8fa46a`, `d986d2b`, `743809b`).
- HardwareInfo bug fixed; smoke test passes in sandbox (no torch);
  host can now import and run `materialize_references.py` and
  `stage2_oneshot.py` past the previous `AttributeError`.
- Golden SHA intact, no MP3s are used as clone conditioning, no
  silent VoiceDesign fallback, QC/retry/final-gate fixes preserved.
- **STAGE 2 (real "Hello my friend.") and subsequent generation tests
  MUST still be run on the RTX 5060 host** — this sandbox has no
  torch/CUDA/models and cannot synthesize audio. Human listening is
  mandatory.

**Verdict: architecture and tooling READY; real-audio verdict NOT-YET-READY pending host materialization + STAGE 2 WAVs + human listening.**
