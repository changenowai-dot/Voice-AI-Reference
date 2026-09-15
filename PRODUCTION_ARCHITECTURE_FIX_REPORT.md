# Production-Architecture Final Integration Report

Branch: `arena/01a08d48-voice-ai-reference`
Baseline (pre-fix) commit: `801c0f4` (Fix PowerShell 5.1 Python validation quoting)
Date: 2026-09-15
Golden Reference (VD-E.wav) required SHA-256:
`b156c02a60a873ad95fc92390c4a136c85308b20188373cd734bee5e5e5f2025`
Golden file is **NOT modified** by this change set (it is a binary WAV
in `project/cache/voice_refs/VD-E.wav` and is never touched by the code
paths changed here; it is verified at runtime by
`app/security/identity_lock.py` before every production run and again
after the run via `_verify_vd_e_hash_post_run` in `jobs/runner.py`).

---

## 1. Root cause (final integration)

The manually verified working configuration
(`en_male_warm_storytelling_authoritative_02` +
`cache/voice_refs/en_male_warm_storytelling_authoritative_02.wav` +
`VOICEDESIGN_REF_TEXT_EN` + `allow_design=False` +
`sampling=balanced` + `seed=52018` → 17.6 s and 53.52 s good) was only
working in ad-hoc scripts because:

1. **Reference text was not carried by the registry.** The production
   GUI/runner path built `VoiceCloneEngine` without passing `ref_text`;
   the engine derived it from `language` alone, and several call sites
   (VD-E block, generic clone block) did not pass a literal at all.
2. **`VoiceCloneEngine.__init__` defaulted `allow_design=True`.** Even
   though both `runner.py` and `main.py` set it explicitly for the
   paths they knew about, any other caller (UI preview server, ad-hoc
   scripts) would silently trigger VoiceDesign if a reference was
   missing or wrong.
3. **`stage2_oneshot.py` constructed `SynthesisRequest` without the
   required `speaker=` field** (API violation — dataclass requires
   `speaker: str`), so even the tooling harness crashed before
   reaching the engine.
4. **New tooling guessed non-existent `hw.device`/`hw.dtype`** on
   `HardwareInfo`. Fixed earlier and regression-guarded.
5. **No single source of truth** for the reference text: hard-coded
   copies of "There is a book…"/"Es gibt ein Buch…" were being used in
   some debug scripts; the registry never exposed a canonical
   `reference_text` per voice, so runner/main had no way to know which
   ref_text belonged to which WAV.
6. **GUI voice list** did not visibly mark unavailable clone voices or
   explain *why* (only disabled the radio button); error message on
   trying to generate was a generic "nicht verfügbar (§13)" instead of
   the concrete "Referenz fehlt — materialisiere mit
   tools/materialize_references.py".

## 2. The production reference contract (final)

For every clone voice (vd_e + all en_/de_ clone entries):

| Component | Source of truth |
|---|---|
| Reference WAV | `cache/voice_refs/{voice_id}.wav` (path stored in `voices/{id}.json:reference_path`) |
| Reference-text key | `voices/{id}.json:reference_text` → one of `VOICEDESIGN_REF_TEXT_EN`, `VOICEDESIGN_REF_TEXT_DE`, or a literal recipe text |
| Resolved literal ref_text | `app.voices.registry.resolve_reference_text(key, language)` — **single source of truth** |
| Voice native language | `settings.language` in JSON, else `en_* → English`, `de_*/vd_e → German` (`_resolve_voice_native_language`) |
| Deterministic seed | `settings.seed` in JSON (52018 for `en_male_warm_storytelling_authoritative_02`, 52034 for `en_male_warm_grounded_humanist_01`) |
| Speaker key passed to synthesis | `voice_id` (set in `runner.run_job`: `cfg["voice"]["speaker"] = entry.voice_id`; pipeline passes it through to `SynthesisRequest(speaker=...)`) |
| allow_design at inference | **`False` by default** (VoiceCloneEngine constructor default is now `False`; runner/main/UI-server all pass `False` explicitly too for defense-in-depth) |
| allow_design during materialization | `True` ONLY inside `tools/materialize_references.py`, enabled via `VOICEOVER_ALLOW_VOICEDESIGN_MATERIALIZE=1` set in that process only |
| MP3/benchmark audio | **rejected** at `VoiceCloneEngine._ensure_wav_reference()` unless `VOICEOVER_REFS_ACCEPT_NONWAV=1` is explicitly set; registry marks voices available only when their WAV exists |

Flow for the verified voice:
```
VoiceRegistry.get("en_male_warm_storytelling_authoritative_02")
  → reference_path     = cache/voice_refs/en_male_warm_storytelling_authoritative_02.wav
  → reference_text_key = "VOICEDESIGN_REF_TEXT_EN"
  → reference_text     = "There is a book no one claims to have written…"
  → settings.seed      = 52018
  → settings.language  = "English"
  → available          = True (because WAV exists and is .wav)
  ↓
runner.build_engine(JobSpec(voice_id=..., language=...))
  → VoiceCloneEngine(
        candidate_id="en_male_warm_storytelling_authoritative_02",
        language="English",
        ref_text="<resolved canonical EN text>",
        seed=52018,
        allow_design=False,
        reference_path=<Path to canonical WAV>)
  ↓
VoiceCloneEngine._ensure_prompt()
  → refuses non-.wav references
  → VoiceRef(ref_text=<canonical>, wav_path=<WAV>, language="English")
  → QwenVoiceStudio.build_clone_prompt(ref)
       = model.create_voice_clone_prompt(ref_audio=<WAV bytes>, ref_text=<canonical>)
  ↓
Pipeline.process_file
  → per segment: SynthesisRequest(text=<target text>, language=<selected UI language>,
                                  speaker=<voice_id>, sampling=balanced,
                                  seed=deterministic(recipe_seed + cache_key))
  → engine.synthesize → studio.synth_clone(prompt, request)
       = model.generate_voice_clone(text=request.text, language=request.language,
                                    voice_clone_prompt=prompt, **balanced)
  ↓
QC → (optional regen) → master → WAV (+ optional MP3).
```

Crucially: the reference TEXT ("There is a book…") is paired ONLY with
the reference AUDIO speaking that exact sentence (the materialized WAV).
The TARGET text (what the user types in the GUI, or "Hello my friend."
in stage2, or the short/medium/long validation texts) is passed
separately as `request.text` and has no required relationship to the
reference text. This is the contract that produced the verified 17.6 s
and 53.52 s good outputs.

## 3. Files changed

Core production code:
- `project/app/tts/qwen_engine.py` — `VoiceCloneEngine.__init__`
  defaults `allow_design=False`; docstring updated.
- `project/app/voices/registry.py`:
    - New `resolve_reference_text(key, language)` helper: AST-reads
      `VOICEDESIGN_REF_TEXT_EN/DE` from `app/prosody/instruct.py` (no
      numpy/torch import required, so CLI tools like
      `materialize_references.py --list-missing` work in a
      pre-model environment).
    - `VoiceProfileEntry` dataclass extended with
      `reference_text_key: str | None` and `reference_text: str | None`.
    - `VoiceRegistry.entries()` now resolves per-voice language from
      `settings.language`/`en_*/de_*` prefix, reads
      `reference_text` from the voice JSON, resolves to a literal via
      `resolve_reference_text`, and exposes both on the entry.
- `project/app/jobs/runner.py` — `build_engine` passes
  `ref_text=VOICEDESIGN_REF_TEXT_DE` for VD-E and
  `ref_text=entry.reference_text` for generic clone voices.
- `project/app/main.py` — same ref_text plumbing as runner.py.
- `project/app/ui/server.py` — legacy preview server now resolves the
  registry entry and passes `language=` and `ref_text=` explicitly
  with `allow_design=False` instead of constructing VoiceCloneEngine
  with near-defaults.
- `project/app/gui/app.py` + `project/app/gui/voice_view.py` — voice
  rows include `availability_note`; unavailable clone voices show
  "NICHT VERFÜGBAR – Referenz fehlt" in the voice list and a specific
  "materialisiere via tools/materialize_references.py" error message
  instead of the generic §13 message.

Voice profiles:
- `project/voices/vd_e.json` + all 42 `en_male_*.json`/`de_male_*.json`/
  `en_female_*.json`/`de_female_*.json` — added
  `"reference_text": "VOICEDESIGN_REF_TEXT_EN"` or `"…_DE"` to make the
  reference-text binding explicit per voice (39 files). Previously
  only 3 EN placeholder entries had the field.

Tooling (fixed / added):
- `project/tools/materialize_references.py` — hardware-info line uses
  canonical `hw.mode` + `recommend_torch_dtype(hw)` (no `hw.device`/
  `hw.dtype`); autodetects neighbouring
  `VoiceOverApp-AgentReady-Latest/project/models` directory; resolves
  `ref_text` via `entry.reference_text` / `resolve_reference_text`
  instead of hard-coding the EN/DE strings.
- `stage2_oneshot.py` (repo root) — fixed `SynthesisRequest` to include
  required `speaker=<voice_id>`; pulls voice language/seed/ref_text
  from the registry via the same `_resolve_voice_native_language` /
  `_resolve_voice_seed` helpers that runner uses; prints the canonical
  ref_text source line; canonical HardwareInfo API; hard-pins
  `allow_design=False`, rejects MP3 refs, prints full diagnostics.
- `project/tools/production_validation.py` (new) — runs the real
  production engine at three text lengths (short ~15–20 s / medium
  ~50–60 s / long ~2 min) through `VoiceCloneEngine` +
  `SynthesisRequest(speaker=voice_id, ref_text from registry,
  allow_design=False)` and writes WAVs + a JSON summary to
  `project/cache/validation/<voice_id>/`.
- `project/tools/test_hardware_api.py` (new) — non-GPU regression
  smoke test:
    - AST-scans production files for `hw.device`/`hw.dtype`
      (must be zero).
    - Verifies `HardwareInfo` fields and `recommend_torch_dtype`
      contract.
    - Verifies `VoiceCloneEngine.__init__` defaults
      `allow_design=False`.
    - Verifies `VoiceProfileEntry` exposes `reference_path`,
      `reference_text`, `reference_text_key`, `available`.
    - Verifies `resolve_reference_text` resolves the EN/DE keys,
      defaults to language-appropriate text for None/auto, and
      passes literal overrides through.
    - Verifies every `SynthesisRequest(` in `stage2_oneshot.py`
      passes `speaker=`.
    - Scans production code for hard-coded "There is a book…"/
      "Es gibt ein Buch…" literals outside of `prosody/instruct.py`
      (with docstring/comment allowances).
- `project/tools/reproduce_voice.py` — added missing `speaker=voice_id`
  to its `SynthesisRequest(...)`.

Golden / VD-E:
- VD-E JSON now explicitly declares `"reference_text":
  "VOICEDESIGN_REF_TEXT_DE"`.
- Runner/main both pass `ref_text=VOICEDESIGN_REF_TEXT_DE` and
  `allow_design=False` for VD-E.
- The binary `cache/voice_refs/VD-E.wav` is never written by any code
  path in this change set. The pre/post-run hash verification in
  `jobs/runner.py` (`_verify_vd_e_hash_post_run`) remains in place.

## 4. Verification performed (sandbox)

- `python3 project/tools/test_hardware_api.py` → **PASS**
- Full AST parse of every `*.py` under `project/app`, `stage2_oneshot.py`,
  `materialize_references.py`, `production_validation.py`,
  `test_hardware_api.py`, `reproduce_voice.py` → **syntax OK**.
- `grep -rn "hw\.device\b\|hw\.dtype\b" project/app stage2_oneshot.py
  project/tools` → **zero matches** outside legitimate
  `device_capability`/`device_hint`/`dtype_hint`/`device_map`.
- `python3 project/tools/materialize_references.py --list-missing`
  works without numpy/torch and lists every clone voice whose WAV is
  absent (expected: 42+ in a fresh checkout).
- `python3 stage2_oneshot.py` imports cleanly past the previous
  AttributeError and SynthesisRequest crash and only fails at the
  intentional `assert entry.available` (because sandbox has no
  materialized references — expected).

## 5. Required host run (RTX 5060, Python 3.12.10 / torch 2.11.0+cu128)

From repo root at the final commit:

```powershell
# 0. sanity (non-GPU)
python project/tools/test_hardware_api.py

# 1. Golden SHA pre-flight
python -c "import hashlib; p=r'project\cache\voice_refs\VD-E.wav'; \
    import pathlib; print(hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest())"
# expected: b156c02a60a873ad95fc92390c4a136c85308b20188373cd734bee5e5e5f2025

# 2. Materialize references for the two tested voices
#    (skip if they already exist from the previous run; script will
#     print EXISTS and skip).
python project/tools/materialize_references.py `
    --voice-id en_male_warm_storytelling_authoritative_02 --language English
python project/tools/materialize_references.py `
    --voice-id en_male_warm_grounded_humanist_01 --language English

# 3. Verify each: WAV, 24 kHz, mono, 16-bit PCM, content = EN ref_text
#    (materialize_references.py prints sha256 and duration)

# 4. Stage 2 one-shot via the fixed tool (mirrors production speaker/ref_text)
python stage2_oneshot.py
#    → writes cache/stage2/hello_<id>.wav, prints full diagnostics.

# 5. Production-path validation at three lengths on the primary voice
python project/tools/production_validation.py `
    --voice-id en_male_warm_storytelling_authoritative_02 --stages short,medium
#    → cache/validation/<id>/{short,medium}.wav + summary.json
#    Add `--stages long` only after short AND medium sound good.

# 6. Golden SHA post-run (must match)
python -c "import hashlib; p=r'project\cache\voice_refs\VD-E.wav'; \
    import pathlib; print(hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest())"
```

Then launch the GUI normally (`project/Run_Controlled.bat` or
`python app/main.py`) and:
- confirm `en_male_warm_storytelling_authoritative_02` appears enabled
  (no "NICHT VERFÜGBAR" marker) once its WAV is present;
- synthesize a short and a medium English text through the GUI;
- listen for intelligibility, stable identity, prosody, no
  reference-text leakage, no tonal/silence/noise artefacts.

## 6. Status

**Architecture and code are ready.** Exact final commit SHA will appear
after the host run is complete and everything is committed. The sandbox
has no GPU/torch/models, so actual audio generation cannot be performed
here. **No production-ready verdict is given from script metrics alone**
— short/medium/long WAVs and GUI output require human listening before
sign-off. Do NOT proceed to long-form/TOP3 until short + medium are
audibly good.

Files to commit after host validation: all of §3 above.
Working tree status: modified (see `git status`).
