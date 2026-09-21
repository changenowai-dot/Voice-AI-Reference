"""Echter TTS-Aussprache-Regressionstest (läuft auf GPU-Host).

Für die MATHEMATIK-Regressionssätze (Anforderung 8) wird ECHTER Qwen-TTS
über zwei auf dem Release vorhandene DE-Stimmen gefahren:
  - de_male_warm_storytelling_authoritative_01
  - de_male_warm_calm_authoritative_02

Erzeugt pro Stimme einen Ordner pronunciation_tts_regression/<voice>/
mit:
  - je Satz eine WAV-Datei (sent_NN.wav)
  - audit.json: TTS-Erfolg, Dauer, Ersetzungen, QC (Stille/Peak/RMS),
    Audio vorhanden / nicht still.
  - summary.md: übersichtlicher Bericht

Nutzt den produktiven Engine-Pfad (VoiceCloneEngine + QwenModelPool,
gleiche Konstruktion wie in runner.build_engine) und engine.synthesize()
mit der echten SynthesisRequest-API (ohne output_path – das WAV wird
nach synthesize via soundfile aus dem zurückgegebenen numpy-Array
geschrieben). KEINE Simulation, KEIN Workaround.

Offline ohne GPU wird der Test sauber SKIP melden (nicht FAIL).
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


# Voices für den Regressionstest. Es werden NUR Stimmen ausgewählt, für
# die ein deutsches Referenz-Bundle im Release existiert (also
# tatsächlich synthetisiert werden können, siehe
# app/voices/bundles/).
REGRESSION_VOICES = [
    "de_male_warm_storytelling_authoritative_01",
    "de_male_warm_calm_authoritative_02",
]

REGRESSION_SENTENCES = [
    "Mathematik ist die Sprache der Zahlen.",
    "Die Mathematik beschreibt Muster, Mengen und Strukturen.",
    "Ein mathematischer Algorithmus kann komplexe Probleme lösen.",
    "Quantenphysik und Mathematik bilden eine wichtige Grundlage moderner Forschung.",
]


@dataclass
class SentenceAudioResult:
    sentence_index: int
    sentence: str
    voice_id: str
    wav_path: str = ""
    ok: bool = False
    error: str = ""
    duration_s: float = 0.0
    peak: float = 0.0
    rms: float = 0.0
    is_silent: bool = True
    tts_text: str = ""
    replacements: list = field(default_factory=list)
    elapsed_s: float = 0.0


def _qc_check_wav(path: Path) -> tuple[bool, float, float, float, str]:
    """Quick-QC: Datei existiert, >1KB, RMS > -50 dBFS (nicht still), Peak <= 1."""
    try:
        import numpy as np
        import soundfile as sf
    except Exception as e:
        return False, 0.0, 0.0, 0.0, f"soundfile/numpy fehlt: {e}"
    if not path.exists():
        return False, 0.0, 0.0, 0.0, f"Datei fehlt: {path}"
    if path.stat().st_size < 1024:
        return False, 0.0, 0.0, 0.0, f"Datei zu klein ({path.stat().st_size} B)"
    try:
        data, sr = sf.read(str(path))
    except Exception as e:
        return False, 0.0, 0.0, 0.0, f"Read fehlgeschlagen: {e}"
    if data is None or len(data) == 0:
        return False, 0.0, 0.0, 0.0, "Leeres Audio"
    arr = data if hasattr(data, "ndim") and data.ndim == 1 else data.mean(axis=1)
    peak = float(abs(arr).max()) if len(arr) else 0.0
    rms = float((arr ** 2).mean() ** 0.5) if len(arr) else 0.0
    dur = float(len(arr) / sr) if sr else 0.0
    silent = rms < 0.002   # ~ -54 dBFS
    if silent:
        return False, dur, peak, rms, "Audio ist still (RMS < -54 dBFS)"
    if peak > 1.01:
        return False, dur, peak, rms, f"Clipping (Peak {peak:.3f})"
    return True, dur, peak, rms, ""


def _build_engine_for_voice(voice_id: str):
    """Baut eine produktionskonforme VoiceCloneEngine – nach dem gleichen
    Muster wie jobs.runner.build_engine() für clone-Stimmen."""
    from app.hardware.detector import detect_hardware
    from app.jobs.runner import _resolve_voice_native_language, _resolve_voice_seed
    from app.security.identity_lock import load_production
    from app.tts.qwen_engine import VoiceCloneEngine
    from app.voices.registry import VoiceRegistry
    from app.prosody.instruct import (ENGLISH_VOICEDESIGN_DESCRIPTIONS,
                                      VOICEDESIGN_DESCRIPTIONS)

    hw = detect_hardware()
    if hw.mode == "cpu" and not hw.gpu_name:
        raise RuntimeError(
            "Keine CUDA-GPU – der TTS-Regressionstest braucht eine GPU.")
    registry = VoiceRegistry()
    entry = registry.get(voice_id)
    if entry is None:
        raise RuntimeError(f"Stimme unbekannt: {voice_id}")
    if not entry.available:
        raise RuntimeError(
            f"Stimme {voice_id} ist nicht verfügbar "
            f"(Referenz-Bundle fehlt oder ungültig).")
    voice_lang = _resolve_voice_native_language(registry, entry)
    seed = _resolve_voice_seed(registry, entry)
    production = load_production()
    adv = {}
    try:
        from app import config as cfgmod
        adv = cfgmod.load_config().get("advanced", {})
    except Exception:
        pass
    desc_entry = (ENGLISH_VOICEDESIGN_DESCRIPTIONS.get(voice_id)
                  or VOICEDESIGN_DESCRIPTIONS.get(voice_id) or {})
    description = (desc_entry.get("description")
                   or entry.description or f"{voice_lang} narrator")
    eng = VoiceCloneEngine(
        hw, candidate_id=voice_id,
        description=description,
        language=voice_lang,
        ref_text=None,
        seed=seed,
        models_dir=None,
        attn_implementation=adv.get("attn_implementation") or None,
        allow_design=False,
        reference_path=None)
    # Speaker = voice_id für Clone-Stimmen (wie im Runner)
    speaker = ("VD-E" if voice_id == "vd_e" else voice_id)
    return eng, entry, voice_lang, speaker


def _write_wav(path: Path, waveform, sr: int) -> None:
    """Schreibt das von engine.synthesize zurückgegebene float32-mono-Array
    als 24-bit PCM WAV (Produktionsstandard)."""
    import numpy as np
    import soundfile as sf
    arr = np.asarray(waveform, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr.mean(axis=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), arr, int(sr), subtype="PCM_24")


def _synth(engine, text: str, language: str, speaker: str,
           wav_path: Path) -> tuple[bool, float, str, object, int]:
    """Ruft engine.synthesize mit der echten SynthesisRequest-API auf und
    schreibt das Ergebnis als WAV. Gibt (ok, elapsed_s, error, result, sr)."""
    from app.tts.engine_base import SynthesisRequest
    t0 = time.perf_counter()
    try:
        req = SynthesisRequest(
            text=text,
            language=language,
            speaker=speaker,
            max_seconds_hint=60.0,
            speed=1.0,
        )
        res = engine.synthesize(req)
        elapsed = time.perf_counter() - t0
        _write_wav(wav_path, res.waveform, res.sample_rate)
        return True, elapsed, "", res, res.sample_rate
    except Exception as e:
        import traceback
        return False, 0.0, f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1200:]}", None, 0


def _tts_preprocess(text: str) -> tuple[str, list]:
    from app.pronunciation import PronunciationEngine
    from app.text.normalize import normalize_text
    norm = normalize_text(text, "German")
    eng = PronunciationEngine()
    p = eng.process(norm, "German", suggest_unknown=False)
    return p.text, [{"from": r["from"], "to": r["to"], "rule": r.get("rule", "")}
                    for r in p.replacements]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=PROJECT_ROOT / "output" / "pronunciation_tts_regression")
    ap.add_argument("--skip-if-no-gpu", action="store_true",
                    help="Beende mit Code 0 (SKIP) wenn keine CUDA-GPU verfügbar.")
    ap.add_argument("--voice", action="append",
                    help="Nur diese Stimme testen (kann mehrfach angegeben werden)")
    args = ap.parse_args()

    # GPU-Check (nur Warnung – der Test darf auch auf CPU laufen, um die
    # API/Schreib/QC-Pfade zu validieren; echte Qwen-Qualitätsprüfung
    # braucht natürlich CUDA).
    have_cuda = False
    try:
        import torch  # noqa
        have_cuda = torch.cuda.is_available()
    except Exception as e:
        if args.skip_if_no_gpu:
            print(f"SKIP (torch/CUDA nicht verfügbar): {e}")
            return 0
        print(f"HINWEIS: torch/CUDA nicht verfügbar – versuche trotzdem: {e}")
    if not have_cuda:
        print("HINWEIS: Keine CUDA-GPU erkannt; Synthese läuft ggf. auf CPU "
              "(sehr langsam) oder schlägt fehl.")

    voices = args.voice or REGRESSION_VOICES
    args.out.mkdir(parents=True, exist_ok=True)
    all_results: list[SentenceAudioResult] = []
    overall_ok = True

    for voice_id in voices:
        vdir = args.out / voice_id
        vdir.mkdir(parents=True, exist_ok=True)
        print(f"\n=== Stimme: {voice_id} ===")
        try:
            engine, entry, lang, speaker = _build_engine_for_voice(voice_id)
        except Exception as e:
            print(f"  FAIL engine build: {e}")
            overall_ok = False
            continue
        try:
            engine.load()
        except Exception as e:
            import traceback
            print(f"  FAIL engine.load: {e}")
            traceback.print_exc()
            overall_ok = False
            continue
        for i, sent in enumerate(REGRESSION_SENTENCES, 1):
            tts_text, repls = _tts_preprocess(sent)
            wav = vdir / f"sent_{i:02d}.wav"
            ok, elapsed, err, res, sr = _synth(
                engine, tts_text, "German", speaker, wav)
            qc_ok, dur, peak, rms, qc_err = (False, 0.0, 0.0, 0.0, "")
            if ok:
                qc_ok, dur, peak, rms, qc_err = _qc_check_wav(wav)
                if not qc_ok:
                    err = qc_err
            res_obj = SentenceAudioResult(
                sentence_index=i, sentence=sent, voice_id=voice_id,
                wav_path=str(wav),
                ok=ok and qc_ok, error=err or qc_err,
                duration_s=dur, peak=peak, rms=rms, is_silent=(rms < 0.002),
                tts_text=tts_text, replacements=repls, elapsed_s=elapsed)
            all_results.append(res_obj)
            flag = "OK" if res_obj.ok else "FAIL"
            print(f"  [{flag}] Satz {i}: {sent}")
            print(f"         TTS: {tts_text[:120]}")
            print(f"         Dauer {elapsed:.1f}s, Audio {dur:.1f}s, "
                  f"peak={peak:.3f}, rms={rms:.4f}, sr={sr}")
            if not res_obj.ok:
                print(f"         ! {res_obj.error}")
                overall_ok = False
        try:
            engine.unload()
        except Exception:
            pass
        # ggf. CUDA-Cache leeren, damit die zweite Stimme nicht OOM läuft
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass

    summary = {
        "final": "PASS" if overall_ok else "FAIL",
        "voices": voices,
        "sentences": REGRESSION_SENTENCES,
        "results": [asdict(r) for r in all_results],
    }
    (args.out / "audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    # Markdown-Bericht
    lines = ["# Aussprache-TTS-Regression", "",
             f"Ergebnis: **{summary['final']}**", "",
             f"Getestete Stimmen: {', '.join(voices)}", "",
             "| Stimme | Satz | OK | Synthese-Dauer | Audio-Dauer | Peak | RMS | TTS-Text |",
             "|---|---|---|---|---|---|---|---|"]
    for r in all_results:
        lines.append(
            f"| {r.voice_id} | {r.sentence_index} | "
            f"{'✅' if r.ok else '❌'} | {r.elapsed_s:.1f}s | {r.duration_s:.1f}s | "
            f"{r.peak:.3f} | {r.rms:.4f} | {r.tts_text[:80]} |")
    lines.append("")
    lines.append("## Ersetzungen")
    for r in all_results:
        lines.append(f"- **{r.voice_id} Satz {r.sentence_index}**:")
        for rep in r.replacements:
            lines.append(f"  - `{rep['from']}` → `{rep['to']}` (*{rep['rule']}*)")
    (args.out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nFINAL_TTS_PRONUNCIATION_REGRESSION={summary['final']}")
    print(f"Reports in {args.out}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
