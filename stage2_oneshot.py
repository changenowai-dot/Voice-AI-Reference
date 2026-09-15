#!/usr/bin/env python3
"""
STAGE 2 one-shot smoke test — correct reference architecture.

Run on RTX 5060 host AFTER materializing references:
    python project/tools/materialize_references.py \
        --voice-id en_male_warm_storytelling_authoritative_02 \
        --language English
    python project/tools/materialize_references.py \
        --voice-id en_male_warm_grounded_humanist_01 \
        --language English

Then (from repo root):
    python stage2_oneshot.py

This script hard-pins allow_design=False and refuses to run if the
production reference WAV is missing or is an MP3 — NO fallback, NO
silent VoiceDesign, NO corrupt-prompt path.
"""
from __future__ import annotations
import contextlib
import hashlib
import os
import sys
import time
import wave
from pathlib import Path

# Locate project directory robustly: script lives at repo root OR one
# level up from project/tools.
_THIS = Path(__file__).resolve()
for _candidate in (_THIS.parent / "project", _THIS.parent):
    if (_candidate / "app" / "tts" / "qwen_engine.py").exists():
        ROOT = _candidate
        break
else:
    raise SystemExit("Cannot locate project/ directory")
sys.path.insert(0, str(ROOT))

# HARD GUARD: disable materialization/MP3 transcode for this test —
# we are testing the production clone path only.
os.environ.pop("VOICEOVER_ALLOW_VOICEDESIGN_MATERIALIZE", None)
os.environ.pop("VOICEOVER_REFS_ACCEPT_NONWAV", None)

# Try to locate an existing models directory (host may have models in
# an adjacent VoiceOverApp install). If found, point the app at it.
def _locate_models_dir() -> Path | None:
    candidates = []
    if os.environ.get("VOICEOVER_MODELS_DIR"):
        candidates.append(Path(os.environ["VOICEOVER_MODELS_DIR"]))
    candidates.append(ROOT / "models")
    # Windows-style sibling install common on host
    for parent in [ROOT.parent, ROOT.parent.parent]:
        cand = parent / "VoiceOverApp-AgentReady-Latest" / "project" / "models"
        candidates.append(cand)
    for c in candidates:
        if c.exists() and (c / "Qwen3-TTS-12Hz-1.7B-Base").exists():
            return c
        if c.exists() and (c / "hf").exists():
            return c
    return None

_models = _locate_models_dir()
if _models is not None:
    os.environ["VOICEOVER_MODELS_DIR"] = str(_models)

OUT = ROOT / "cache" / "stage2"
OUT.mkdir(parents=True, exist_ok=True)

from app.voices.registry import VoiceRegistry              # noqa: E402
from app.hardware.detector import detect_hardware, recommend_torch_dtype  # noqa: E402
from app.tts.qwen_engine import VoiceCloneEngine           # noqa: E402
from app.tts.sampler import params_for_set                 # noqa: E402
from app.jobs.runner import (_resolve_voice_native_language,
                             _resolve_voice_seed)          # noqa: E402
from app.tts.engine_base import SynthesisRequest           # noqa: E402
from app import paths as _p                                # noqa: E402

VOICES = [
    "en_male_warm_storytelling_authoritative_02",
    "en_male_warm_grounded_humanist_01",
]
TEXT = "Hello my friend."


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def wav_info(p: Path):
    with contextlib.closing(wave.open(str(p), "rb")) as w:
        return (w.getframerate(), w.getnchannels(), w.getsampwidth() * 8,
                w.getnframes() / float(w.getframerate()))


def main():
    reg = VoiceRegistry()
    hw = detect_hardware()
    device = "cuda" if hw.mode.startswith("gpu") else "cpu"
    dtype = recommend_torch_dtype(hw)
    print(f"[stage2] mode={hw.mode} device={device} dtype={dtype} "
          f"gpu={hw.gpu_name or 'none'}")
    print(f"[stage2] MODELS_DIR={os.environ.get('VOICEOVER_MODELS_DIR') or _p.MODELS_DIR}")
    print(f"[stage2] HARD-GUARD: allow_design=False, no MP3 accepted")
    for vid in VOICES:
        entry = reg.get(vid)
        assert entry is not None, f"voice {vid} not in registry"
        voice_language = _resolve_voice_native_language(reg, entry)
        voice_seed = _resolve_voice_seed(reg, entry) or 42
        assert entry.available, (
            f"{vid} unavailable — materialize production reference first via "
            "python project/tools/materialize_references.py "
            f"--voice-id {vid} --language {voice_language}")
        rp = _p.ROOT / entry.reference_path
        assert rp.exists(), f"ref MISSING: {rp}"
        assert rp.suffix.lower() == ".wav", f"ref must be WAV, got {rp}"
        canonical_ref_text = entry.reference_text
        assert canonical_ref_text, f"no canonical reference_text for {vid}"
        ref_sha = sha256(rp)
        sr, nch, bd, ref_dur = wav_info(rp)
        print(f"\n[stage2] === {vid} ===")
        print(f"  voice_id:            {vid}")
        print(f"  reference file:      {rp}")
        print(f"  reference sha256:    {ref_sha}")
        print(f"  reference sr/ch/bd:  {sr} Hz / {nch} ch / {bd} bit")
        print(f"  reference duration:  {ref_dur:.2f} s")
        print(f"  backend_mode:        {entry.backend_mode}")
        print(f"  language:            {voice_language}")
        print(f"  allow_design:        False (hard-pinned)")
        print(f"  base model:          Qwen/Qwen3-TTS-12Hz-1.7B-Base (VoiceClone)")
        print(f"  seed (from recipe):  {voice_seed}")
        print(f"  ref_text source:     VoiceRegistry.resolve_reference_text()")
        print(f"  ref_text used:       {canonical_ref_text[:80]}…")
        eng = VoiceCloneEngine(
            hw, candidate_id=entry.voice_id,
            description=entry.description or "",
            language=voice_language,
            ref_text=canonical_ref_text,
            seed=voice_seed,
            models_dir=None,
            attn_implementation=None,
            allow_design=False,           # HARD PIN
            reference_path=rp,
        )
        try:
            eng.load()
            print("  clone prompt:        built (cached by candidate_id:mtime)")
            # speaker is the canonical Cache key for clone voices:
            # the voice_id (runner.py sets cfg["voice"]["speaker"] = voice_id).
            req = SynthesisRequest(
                text=TEXT, language=voice_language,
                speaker=entry.voice_id,
                sampling=params_for_set("balanced"), seed=voice_seed,
                max_seconds_hint=10.0)
            t0 = time.perf_counter()
            result = eng.synthesize(req)
            dt = time.perf_counter() - t0
            import numpy as np
            wav = result.waveform
            sr_out = result.sample_rate
            arr = wav if isinstance(wav, np.ndarray) else wav.cpu().numpy()
            arr = arr.reshape(-1).astype("float32")
            out = OUT / f"hello_{vid}.wav"
            from app.audio.io import write_wav
            write_wav(out, arr, sr_out, bit_depth=16)
            out_sr, out_ch, out_bd, out_dur = wav_info(out)
            rms = float(np.sqrt(np.mean(arr.astype("float32") ** 2)))
            has_nan = bool(np.isnan(arr).any())
            peak = float(np.abs(arr).max())
            print(f"  synth time:          {dt:.1f} s")
            print(f"  output file:         {out}")
            print(f"  output sr/ch/bd:     {out_sr} / {out_ch} / {out_bd}")
            print(f"  output duration:     {out_dur:.2f} s")
            print(f"  output RMS:          {rms:.4f}")
            print(f"  output peak:         {peak:.4f}")
            print(f"  output NaN:          {has_nan}")
            ok = out_dur > 0.8 and rms > 0.01 and not has_nan and peak < 1.0
            print(f"  --------------------")
            print(f"  AUTOMATIC CHECK:     {'PASS' if ok else 'FAIL'}")
            print(f"  REQUIRED:            HUMAN LISTENING before marking ready")
        finally:
            eng.unload()


if __name__ == "__main__":
    main()
