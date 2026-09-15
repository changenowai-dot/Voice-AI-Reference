#!/usr/bin/env python3
"""
STAGE 2 one-shot smoke test — CORRECT reference architecture.

Run on RTX 5060 host AFTER materializing references:
    python project/tools/materialize_references.py \
        --voice-id en_male_warm_storytelling_authoritative_02 \
        --language English
    python project/tools/materialize_references.py \
        --voice-id en_male_warm_grounded_humanist_01 \
        --language English

Then:
    python stage2_oneshot.py

This script hard-pins allow_design=False and refuses to run if the
production reference WAV is missing or is an MP3 — NO fallback, NO
silent VoiceDesign, NO corrupt-prompt path.
"""
from __future__ import annotations
import hashlib
import os
import sys
import time
import wave
import contextlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "project"
sys.path.insert(0, str(ROOT))

# HARD GUARD: disable materialization/MP3 transcode for this test —
# we are testing the production clone path only.
os.environ.pop("VOICEOVER_ALLOW_VOICEDESIGN_MATERIALIZE", None)
os.environ.pop("VOICEOVER_REFS_ACCEPT_NONWAV", None)

OUT = ROOT / "cache" / "stage2"
OUT.mkdir(parents=True, exist_ok=True)

from app.voices.registry import VoiceRegistry          # noqa: E402
from app.hardware.detector import detect_hardware            # noqa: E402
from app.tts.qwen_engine import VoiceCloneEngine       # noqa: E402
from app.tts.sampler import params_for_set             # noqa: E402
from app.prosody.instruct import VOICEDESIGN_REF_TEXT_EN, VOICEDESIGN_REF_TEXT_DE  # noqa: E402
from app.tts.engine_base import SynthesisRequest       # noqa: E402
from app import paths as _p                            # noqa: E402

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
        return w.getframerate(), w.getnchannels(), w.getsampwidth()*8, \
               w.getnframes()/float(w.getframerate())


def main():
    reg = VoiceRegistry()
    hw = detect_hardware()
    print(f"[stage2] device={hw.device} dtype={hw.dtype}")
    print(f"[stage2] HARD-GUARD: allow_design=False, no MP3 accepted")
    for vid in VOICES:
        entry = reg.get(vid)
        assert entry is not None, f"voice {vid} not in registry"
        assert entry.available, (
            f"{vid} unavailable — materialize production reference first via "
            "python project/tools/materialize_references.py "
            f"--voice-id {vid} --language English")
        rp = _p.ROOT / entry.reference_path
        assert rp.exists(), f"ref MISSING: {rp}"
        assert rp.suffix.lower() == ".wav", f"ref must be WAV, got {rp}"
        ref_sha = sha256(rp)
        sr, nch, bd, ref_dur = wav_info(rp)
        print(f"\n[stage2] === {vid} ===")
        print(f"  reference file:      {rp}")
        print(f"  reference sha256:    {ref_sha}")
        print(f"  reference sr/ch/bd:  {sr} Hz / {nch} ch / {bd} bit")
        print(f"  reference duration:  {ref_dur:.2f} s")
        print(f"  backend_mode:        {entry.backend_mode}")
        print(f"  language:            English")
        print(f"  allow_design:        False (hard-pinned)")
        print(f"  base model:          Qwen/Qwen3-TTS-12Hz-1.7B-Base (VoiceClone)")
        print(f"  ref_text used:       {VOICEDESIGN_REF_TEXT_EN[:80]}…")
        eng = VoiceCloneEngine(
            hw, candidate_id=entry.voice_id,
            description=entry.description or "",
            language="English",
            seed=42,
            models_dir=None,
            attn_implementation=None,
            allow_design=False,           # HARD PIN
            reference_path=rp,
        )
        try:
            eng.load()
            print("  clone prompt:        built (cached by candidate_id:mtime)")
            req = SynthesisRequest(
                text=TEXT, language="English",
                sampling=params_for_set("balanced"), seed=42,
                max_seconds_hint=10.0)
            t0 = time.time()
            result = eng.synthesize(req)
            dt = time.time() - t0
            wav = result.waveform
            sr_out = result.sample_rate
            import numpy as np
            arr = wav if isinstance(wav, np.ndarray) else wav.cpu().numpy()
            arr = arr.reshape(-1).astype("float32")
            out = OUT / f"hello_{vid}.wav"
            from app.audio.io import write_wav
            write_wav(out, arr, sr_out)
            out_sr, out_ch, out_bd, out_dur = wav_info(out)
            rms = float(np.sqrt(np.mean(arr.astype("float32")**2)))
            has_nan = bool(np.isnan(arr).any())
            print(f"  synth time:          {dt:.1f} s")
            print(f"  output file:         {out}")
            print(f"  output sr/ch/bd:     {out_sr} / {out_ch} / {out_bd}")
            print(f"  output duration:     {out_dur:.2f} s")
            print(f"  output RMS:          {rms:.4f}")
            print(f"  output NaN:          {has_nan}")
            ok = out_dur > 0.8 and rms > 0.01 and not has_nan
            print(f"  --------------------")
            print(f"  AUTOMATIC CHECK:     {'PASS' if ok else 'FAIL'}")
            print(f"  REQUIRED:            HUMAN LISTENING before marking ready")
        finally:
            eng.unload()


if __name__ == "__main__":
    main()
