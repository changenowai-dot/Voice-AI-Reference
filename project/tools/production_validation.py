#!/usr/bin/env python3
"""Production-path validation for a validated clone voice.

Runs the REAL production pipeline (runner.Pipeline + SynthesisRequest
with speaker=<voice_id>, ref_text from registry, allow_design=False)
through three text lengths:
    A) short   (~15-20 s)
    B) medium  (~50-60 s)
    C) long    (~2 min)

Outputs go to project/cache/validation/<voice_id>/{short,medium,long}.wav
plus a JSON summary. This does NOT touch the GUI job system or mp3
mastering beyond what the production pipeline itself does.

Usage (RTX 5060 host):
  python project/tools/production_validation.py \
      --voice-id en_male_warm_storytelling_authoritative_02
"""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import json
import os
import sys
import time
import wave
from pathlib import Path

_THIS = Path(__file__).resolve()
ROOT = _THIS.parents[2]
PROJECT = ROOT / "project"
sys.path.insert(0, str(PROJECT))

# Production-safe defaults: no silent design, no MP3 transcode.
os.environ.pop("VOICEOVER_ALLOW_VOICEDESIGN_MATERIALIZE", None)
os.environ.pop("VOICEOVER_REFS_ACCEPT_NONWAV", None)


def _locate_models_dir() -> Path | None:
    if os.environ.get("VOICEOVER_MODELS_DIR"):
        p = Path(os.environ["VOICEOVER_MODELS_DIR"])
        if p.exists():
            return p
    for c in [
        PROJECT / "models",
        ROOT.parent / "VoiceOverApp-AgentReady-Latest" / "project" / "models",
        ROOT.parent.parent / "VoiceOverApp-AgentReady-Latest" / "project" / "models",
    ]:
        if c.exists() and (
            (c / "Qwen3-TTS-12Hz-1.7B-Base").exists() or (c / "hf").exists()
        ):
            return c
    return None


_m = _locate_models_dir()
if _m is not None:
    os.environ["VOICEOVER_MODELS_DIR"] = str(_m)


SHORT_EN = "Hello my friend. This is a short listening test for the warm " \
           "storytelling voice."

MEDIUM_EN = ("There is a quiet dignity in a voice that does not need to shout "
             "to be heard. A voice that pauses, that lets a thought land "
             "before moving on — the way old friends speak in a room of "
             "bookshelves, confident that you will stay long enough to hear "
             "the rest. In documentaries this matters. Every sentence carries "
             "weight, every pause signals something worth remembering. If the "
             "narrator sounds certain without sounding arrogant, the audience "
             "leans in. They do not merely listen. They trust. And trust is "
             "the rarest currency in a world of shouting.")

LONG_EN = (
    "Generations have argued about what makes a voice feel like home. "
    "Some say it is the pitch, others the cadence, still others the "
    "slight regional coloring that hints at where the speaker grew up. "
    "But anyone who has ever listened long enough to a trusted narrator "
    "knows the truth: what draws us in is restraint. The voice that does "
    "not need to perform, that does not rush to the next line, that treats "
    "every sentence as though it has earned its place in the script.\n\n"
    "That is why documentary narration has always demanded a different "
    "kind of actor. Not the loudest in the room. Not the most theatrical. "
    "Rather, the person who can say 'and then the world changed' as though "
    "you and they are sitting together, watching it change again in real "
    "time. Authority without arrogance. Warmth without sentimentality. "
    "Clarity that respects the listener's intelligence.\n\n"
    "When such a voice meets a script worth hearing, something quiet and "
    "remarkable happens: listeners forget they are listening to a recording. "
    "They forget the technology between the narrator's mouth and their own "
    "ears. They simply hear. They follow. They remember. And that, in the "
    "end, is the only real measure of whether a synthetic voice has earned "
    "the right to tell a story.")


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _wav_info(p: Path):
    with contextlib.closing(wave.open(str(p), "rb")) as w:
        return (w.getframerate(), w.getnchannels(), w.getsampwidth() * 8,
                w.getnframes() / float(w.getframerate()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice-id", required=True)
    ap.add_argument("--language", default="English",
                    choices=["English", "German"])
    ap.add_argument("--stages", default="short,medium,long",
                    help="comma-separated subset of short,medium,long")
    args = ap.parse_args()

    from app.hardware.detector import detect_hardware, recommend_torch_dtype
    from app.jobs.runner import (_resolve_voice_native_language,
                                 _resolve_voice_seed)
    from app.tts.engine_base import SynthesisRequest
    from app.tts.qwen_engine import VoiceCloneEngine
    from app.tts.sampler import params_for_set
    from app.voices.registry import VoiceRegistry
    from app.audio.io import write_wav
    from app import paths as _p
    import numpy as np

    hw = detect_hardware()
    device = "cuda" if hw.mode.startswith("gpu") else "cpu"
    dtype = recommend_torch_dtype(hw)
    print(f"[validate] mode={hw.mode} device={device} dtype={dtype} "
          f"gpu={hw.gpu_name or 'none'}")

    reg = VoiceRegistry()
    entry = reg.get(args.voice_id)
    if entry is None:
        raise SystemExit(f"unknown voice: {args.voice_id}")
    voice_lang = _resolve_voice_native_language(reg, entry)
    voice_seed = _resolve_voice_seed(reg, entry) or 52018
    print(f"[validate] voice={entry.voice_id} lang={voice_lang} "
          f"backend={entry.backend_mode} seed={voice_seed}")

    rp = _p.ROOT / entry.reference_path
    assert rp.exists() and rp.suffix.lower() == ".wav", \
        f"ref must exist as WAV: {rp}"
    assert entry.reference_text, f"no canonical ref_text for {entry.voice_id}"
    print(f"[validate] ref={rp.name} sha={_sha256(rp)[:16]}…")

    out_dir = _p.CACHE_DIR / "validation" / entry.voice_id
    out_dir.mkdir(parents=True, exist_ok=True)

    texts = {"short": SHORT_EN if voice_lang == "English" else SHORT_EN,
             "medium": MEDIUM_EN if voice_lang == "English" else MEDIUM_EN,
             "long": LONG_EN if voice_lang == "English" else LONG_EN}
    # NOTE: the DE texts above are placeholders; the canonical tested
    # configuration today is English. Long German texts can be added later.

    eng = VoiceCloneEngine(
        hw, candidate_id=entry.voice_id,
        description=entry.description or "",
        language=voice_lang,
        ref_text=entry.reference_text,
        seed=voice_seed,
        models_dir=None,
        allow_design=False,
        reference_path=rp,
    )
    summary = {"voice_id": entry.voice_id, "language": voice_lang,
               "ref_text_source": "VoiceRegistry",
               "ref_sha256": _sha256(rp),
               "allow_design": False, "speaker": entry.voice_id,
               "runs": {}}
    try:
        eng.load()
        for stage in args.stages.split(","):
            stage = stage.strip()
            if stage not in texts:
                continue
            text = texts[stage]
            max_s = {"short": 20.0, "medium": 80.0, "long": 200.0}[stage]
            print(f"\n=== {stage.upper()} ({len(text)} chars, ~est {max_s:.0f}s) ===")
            req = SynthesisRequest(
                text=text, language=voice_lang, speaker=entry.voice_id,
                sampling=params_for_set("balanced"),
                seed=voice_seed, max_seconds_hint=max_s)
            t0 = time.perf_counter()
            res = eng.synthesize(req)
            dt = time.perf_counter() - t0
            arr = res.waveform
            if not isinstance(arr, np.ndarray):
                arr = arr.cpu().numpy()
            arr = arr.reshape(-1).astype("float32")
            out = out_dir / f"{stage}.wav"
            write_wav(out, arr, res.sample_rate, bit_depth=16)
            sr, ch, bd, dur = _wav_info(out)
            rms = float(np.sqrt(np.mean(arr.astype("float32") ** 2)))
            peak = float(np.abs(arr).max())
            has_nan = bool(np.isnan(arr).any())
            ok = dur > 0.8 and rms > 0.01 and not has_nan and peak < 1.0
            rec = {"file": str(out), "sample_rate": sr, "channels": ch,
                   "bit_depth": bd, "duration_s": round(dur, 2),
                   "elapsed_s": round(dt, 2), "rms": round(rms, 4),
                   "peak": round(peak, 4), "nan": has_nan,
                   "automatic_pass": ok,
                   "human_listening_required": True}
            summary["runs"][stage] = rec
            print(f"  out={out.name}  dur={dur:.2f}s  rms={rms:.4f}  "
                  f"peak={peak:.3f}  nan={has_nan}  elapsed={dt:.1f}s  "
                  f"AUTO={'PASS' if ok else 'FAIL'}")
            print(f"  REQUIRED: human listening before production sign-off")
    finally:
        eng.unload()

    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                            encoding="utf-8")
    print(f"\nsummary -> {summary_path}")


if __name__ == "__main__":
    main()
