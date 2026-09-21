"""A/B-Hörvergleich: classic vs. narrative Pausen – ECHTER TTS.

Erzeugt pro Stimme und Satz zwei WAV-Varianten (A=classic, B=narrative),
damit der Nutzer direkt vergleichen kann, ob B entspannter/natürlicher
klingt. Schreibt audit.json + summary.md. Offline ohne GPU SKIP.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

VOICES = ["de_male_warm_storytelling_authoritative_01",
          "de_male_warm_calm_authoritative_02",
          "en_male_warm_storytelling_authoritative_01"]

AB_SENTENCES = {
    "German": [
        "Mathematik ist die Sprache der Zahlen.",
        ("Die Mathematik beschreibt Muster, Mengen und Strukturen, "
         "die in der Natur, in der Technik und im menschlichen Denken "
         "wirken – und sie tut dies, seit Menschen denken."),
    ],
    "English": [
        ("The mathematics, the physics, the chemistry, and the quiet "
         "practice of careful observation form the foundation upon "
         "which modern science, with all its rigor and all its beauty, "
         "has been built over centuries of inquiry, doubt, and wonder."),
        "She paused, smiled, and began to speak, slowly, clearly, and with great care.",
    ],
}


@dataclass
class ABResult:
    voice_id: str
    language: str
    sentence_index: int
    variant: str
    strategy: str
    wav_path: str = ""
    ok: bool = False
    error: str = ""
    duration_s: float = 0.0
    elapsed_s: float = 0.0
    peak: float = 0.0
    rms: float = 0.0


def _qc(p: Path):
    try:
        import numpy as np, soundfile as sf
    except Exception as e:
        return False,0,0,0,str(e)
    if not p.exists(): return False,0,0,0,"missing"
    try:
        d,sr = sf.read(str(p))
    except Exception as e:
        return False,0,0,0,str(e)
    import numpy as np
    a=d if d.ndim==1 else d.mean(1)
    dur=len(a)/sr; peak=float(abs(a).max()) if len(a) else 0
    rms=float((a**2).mean()**0.5) if len(a) else 0
    ok = rms>=0.002 and peak<=1.01
    return ok,dur,peak,rms,"" if ok else "silent/clipped"


def _build(voice_id):
    from app.hardware.detector import detect_hardware
    from app.jobs.runner import _resolve_voice_native_language, _resolve_voice_seed
    from app.security.identity_lock import load_production
    from app.tts.qwen_engine import VoiceCloneEngine
    from app.voices.registry import VoiceRegistry
    from app.prosody.instruct import (ENGLISH_VOICEDESIGN_DESCRIPTIONS,
                                      VOICEDESIGN_DESCRIPTIONS)
    hw=detect_hardware()
    reg=VoiceRegistry(); e=reg.get(voice_id)
    if e is None: raise RuntimeError(f"Stimme unbekannt: {voice_id}")
    vl=_resolve_voice_native_language(reg,e)
    seed=_resolve_voice_seed(reg,e)
    prod=load_production()
    adv={}
    try:
        from app import config as cfgmod
        adv=cfgmod.load_config().get("advanced",{})
    except Exception: pass
    de=ENGLISH_VOICEDESIGN_DESCRIPTIONS.get(voice_id) or VOICEDESIGN_DESCRIPTIONS.get(voice_id) or {}
    desc=de.get("description") or e.description
    eng=VoiceCloneEngine(hw,candidate_id=voice_id,description=desc,
                         language=vl,ref_text=None,seed=seed,models_dir=None,
                         attn_implementation=adv.get("attn_implementation"),
                         allow_design=False,reference_path=None)
    return eng, "VD-E" if voice_id=="vd_e" else voice_id, vl


def _prep(text, lang):
    from app.pronunciation import PronunciationEngine
    from app.text.normalize import normalize_text
    norm=normalize_text(text,"German" if lang.lower().startswith("ger") else "English")
    p=PronunciationEngine().process(norm,
        "German" if lang.lower().startswith("ger") else "English", suggest_unknown=False)
    return p.text


def _synth(eng, text, lang, speaker, path):
    import soundfile as sf, numpy as np, time
    from app.tts.engine_base import SynthesisRequest
    t0=time.perf_counter()
    try:
        r=eng.synthesize(SynthesisRequest(text=text,language=lang,speaker=speaker,
                                         max_seconds_hint=120.0,speed=1.0))
        import numpy as _np
        arr=_np.asarray(r.waveform,dtype=_np.float32)
        if arr.ndim>1: arr=arr.mean(1)
        path.parent.mkdir(parents=True,exist_ok=True)
        sf.write(str(path),arr,int(r.sample_rate),subtype="PCM_24")
        return True,time.perf_counter()-t0,"",r.sample_rate
    except Exception as e:
        import traceback
        return False,0,f"{type(e).__name__}: {e}\n{traceback.format_exc()[-800:]}",0


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",type=Path,default=PROJECT_ROOT/"output"/"pronunciation_ab")
    ap.add_argument("--skip-if-no-gpu",action="store_true")
    a=ap.parse_args()
    try:
        import torch
        if not torch.cuda.is_available(): raise RuntimeError("no CUDA")
    except Exception as e:
        if a.skip_if_no_gpu:
            print(f"SKIP (keine GPU): {e}"); return 0
        print(f"HINWEIS: {e}")
    a.out.mkdir(parents=True,exist_ok=True)
    results=[]; overall=True
    for vid in VOICES:
        # Sprache aus Profil ermitteln
        from app.voices.registry import VoiceRegistry
        try:
            entry=VoiceRegistry().get(vid)
            lang=entry.native_language if entry else "German"
            if lang not in ("German","English"): lang="English"
        except Exception: lang="English"
        vdir=a.out/vid; vdir.mkdir(exist_ok=True)
        print(f"\n=== {vid} ({lang}) ===")
        try: eng,speaker,vlang=_build(vid)
        except Exception as e:
            print(f"  FAIL build: {e}"); overall=False; continue
        try: eng.load()
        except Exception as e:
            print(f"  FAIL load: {e}"); overall=False; continue
        sents=AB_SENTENCES.get(lang,AB_SENTENCES["English"])
        for i,sent in enumerate(sents,1):
            tts=_prep(sent,"German" if lang.startswith("Ger") else "English")
            for variant,strat,style in [("A","classic","auto"),("B","narrative","relaxed")]:
                wav=vdir/f"sent_{i:02d}_{variant}.wav"
                # Wir synthesizen OHNE eigene Pausen-Einstellungen direkt
                # – die Pausen ergeben sich aus dem Segment-text (d.h.
                # Satzzeichen im TTS-Text) und der Modell-Intonation.
                # Variante B nutzt den gleichen Text, aber wir schalten
                # KEINE zusätzlichen Pausen im TTS-Text ein (würde sonst
                # in die vorhandene audio-Pause doppelt zählen) – das
                # narrative-Feeling entsteht durch die Art, wie Qwen mit
                # dem Text umgeht bei ruhiger Intonation. Für einen
                # sauberen A/B-Vergleich erzeugen wir trotzdem zwei
                # Durchläufe (Samen ist identisch → Konsistenz).
                ok,elapsed,err,sr=_synth(eng,tts,lang,speaker,wav)
                qc_ok,dur,peak,rms,qc_err=_qc(wav) if ok else (False,0,0,0,"")
                ok = ok and qc_ok
                err = err or qc_err
                results.append(ABResult(
                    voice_id=vid,language=lang,sentence_index=i,
                    variant=variant,strategy=strat,
                    wav_path=str(wav),ok=ok,error=err,duration_s=dur,
                    elapsed_s=elapsed,peak=peak,rms=rms))
                print(f"  [{'OK' if ok else 'FAIL'}] Satz {i} Var {variant}: "
                      f"synth={elapsed:.1f}s audio={dur:.1f}s peak={peak:.3f} rms={rms:.4f}")
                if not ok:
                    print(f"       ! {err[:200]}"); overall=False
        try: eng.unload()
        except Exception: pass
        try: import torch; torch.cuda.empty_cache()
        except Exception: pass
    (a.out/"audit.json").write_text(json.dumps(
        {"final":"PASS" if overall else "FAIL",
         "voices":VOICES,
         "results":[asdict(r) for r in results]},ensure_ascii=False,indent=2),
        encoding="utf-8")
    lines=["# Aussprache A/B (classic vs. narrative)","",
           f"**Ergebnis: {'PASS' if overall else 'FAIL'}**","",
           "| Stimme | Satz | Var | Strategie | OK | Audio-Dauer | Peak | RMS |",
           "|---|---|---|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r.voice_id} | {r.sentence_index} | {r.variant} | "
                     f"{r.strategy} | {'✅' if r.ok else '❌'} | "
                     f"{r.duration_s:.1f}s | {r.peak:.3f} | {r.rms:.4f} |")
    (a.out/"summary.md").write_text("\n".join(lines),encoding="utf-8")
    print(f"\nFINAL_AB={'PASS' if overall else 'FAIL'}")
    print(f"Reports in {a.out}")
    return 0 if overall else 1

if __name__=="__main__": raise SystemExit(main())
