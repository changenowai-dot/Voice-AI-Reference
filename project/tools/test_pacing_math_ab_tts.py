"""A/B-Hoertest: (A) natuerliches Pacing bei speed=1.0 vs. 0.9-Stretch,
(B) "Mathematik" fluent (natuerliche Orthographie) vs. alte Respellings.

Laeuft NUR auf dem GPU-Host (echter Qwen-TTS); ohne CUDA sauberer SKIP.

Varianten PACING (je Stimme & Text):
  V1_current : speed=1.0, kein Pacing-Hint          (aktueller Stand)
  V2_pacing  : speed=1.0 + Pacing-Hint im Instruct  (NEU, nur Erzeugung)
  V3_speed09 : speed_instruct(0.9) + apply_speed(0.9) auf dem fertigen WAV
               (exakte Emulation des bisherigen 0.9-Pfads: atempo-Stretch)

Varianten MATHEMATIK (nur DE-Stimmen, je 4 Regressionssaetze):
  M1_alt : interner Text mit ALTEN Bindestrich-Respellings (Ma-te-MA-tik)
  M2_neu : Produktionspfad nach Patch (natuerliche Orthographie)

Ausgabe: output/pacing_math_ab/<voice>/*.wav + audit.json + summary.md
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import types
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Headless-Tkinter-Stub (wie test_pronunciation_live.py)
try:
    import tkinter  # noqa: F401
except ModuleNotFoundError:
    class _M(types.ModuleType):
        TclError = type("TclError", (Exception,), {})
        class Tk: pass
        class Frame: pass
        class StringVar:
            def __init__(s, *a, **k): pass
            def get(s): return ""
            def set(s, v): pass
        class BooleanVar:
            def __init__(s, *a, **k): pass
            def get(s): return False
            def set(s, v): pass
        class DoubleVar:
            def __init__(s, *a, **k): pass
            def get(s): return 1.0
            def set(s, v): pass
        NONE = N = S = E = W = CENTER = LEFT = RIGHT = TOP = BOTTOM = ""
        HORIZONTAL = VERTICAL = BOTH = ALL = END = X = Y = ""
        DISABLED = NORMAL = ACTIVE = WORD = ""
        def __getattr__(s, n):
            return lambda *a, **k: None
    for _n in ("tkinter", "tkinter.ttk", "tkinter.filedialog",
               "tkinter.messagebox"):
        sys.modules[_n] = _M(_n)

import numpy as np  # noqa: E402

from app import paths  # noqa: E402
paths.ensure_directories()
from app.audio.assemble import apply_speed  # noqa: E402
from app.hardware.detector import detect_hardware  # noqa: E402
from app.jobs.runner import JobSpec, build_engine  # noqa: E402
from app.pronunciation import PronunciationEngine  # noqa: E402
from app.prosody.instruct import pacing_hint, speed_instruct  # noqa: E402
from app.security.identity_lock import load_production  # noqa: E402
from app.text.normalize import NormalizationReport, normalize_text  # noqa: E402
from app.tts.engine_base import SynthesisRequest  # noqa: E402

OUT_DIR = paths.OUTPUT_DIR / "pacing_math_ab"

DE_VOICES = ["de_male_warm_storytelling_authoritative_01",
             "de_male_warm_calm_authoritative_02"]
EN_VOICES = ["en_male_warm_storytelling_authoritative_01"]

PACING_TEXTS = {
    "German": [
        ("de_doc_1",
         "Die Entstehung des Weltalls, die Bildung der ersten Sterne, das "
         "Werden der Galaxien - all diese Vorgaenge vollzogen sich ueber "
         "Zeitraeume, die sich der menschlichen Vorstellungskraft entziehen, "
         "und doch lassen sich ihre Spuren heute noch in jedem Winkel des "
         "Nachthimmels finden."),
        ("de_doc_2",
         "Es sind nicht die grossen Ereignisse, die Geschichte machen, "
         "sondern die leisen Entscheidungen vieler Menschen, die Tag fuer "
         "Tag, oft unbemerkt, die Richtung veraendern, in der eine Gesellschaft "
         "sich bewegt."),
    ],
    "English": [
        ("en_doc_1",
         "The mathematics, the physics, the chemistry, and the quiet "
         "practice of careful observation form the foundation upon which "
         "modern science, with all its rigor and all its beauty, has been "
         "built over centuries of inquiry, doubt, and wonder."),
        ("en_doc_2",
         "It is not the great events that shape history, but the quiet "
         "decisions of many people who, day after day, often unnoticed, "
         "change the direction in which a society is moving."),
    ],
}

MATH_SENTENCES = [
    "Mathematik ist die Sprache der Zahlen.",
    "Die Mathematik beschreibt Muster, Mengen und Strukturen.",
    "Ein mathematischer Algorithmus kann komplexe Probleme lösen.",
    "Quantenphysik und Mathematik bilden eine wichtige Grundlage moderner Forschung.",
]

# ALTOLD Respellings (vor dem Patch) - fuer M1_alt im Hoertest.
OLD_MAP = {
    "Mathematik": "Ma-te-MA-tik",
    "mathematisch": "ma-te-MA-tisch",
    "Mathematische": "Ma-te-MA-ti-sche",
    "mathematische": "ma-te-MA-ti-sche",
    "mathematischen": "ma-te-MA-ti-schen",
    "mathematischer": "ma-te-MA-ti-scher",
    "mathematischem": "ma-te-MA-ti-schem",
}


def apply_old_respellings(text: str) -> str:
    """Wortgrenzen-sicher: alte Respellings fuer den M1_alt-Hoertest."""
    for term in sorted(OLD_MAP, key=len, reverse=True):
        pattern = re.compile(r"(?<![\wÄÖÜäöüß])" + re.escape(term) +
                             r"(?=$|[\-.,;:!?)\]\s]|$)", re.IGNORECASE)
        text = pattern.sub(OLD_MAP[term], text)
    return text


@dataclass
class ABItem:
    voice_id: str
    part: str            # "pacing" | "math"
    label: str           # z. B. V1_current / M2_neu
    text_id: str
    original: str
    tts_text: str
    instruct: str
    post_speed: float    # 1.0 = keine Nachbearbeitung
    language: str = ""   # relevante Konfiguration
    speed: float = 1.0   # Generation-Speed (immer 1.0; Post nur bei V3)
    wav: str = ""
    duration_s: float = 0.0
    elapsed_s: float = 0.0
    peak: float = 0.0
    rms: float = 0.0
    ok: bool = False
    error: str = ""


def _write_wav(path: Path, wav: np.ndarray, sr: int) -> None:
    try:
        import soundfile as sf
        sf.write(str(path), np.asarray(wav, dtype=np.float32), sr,
                 subtype="PCM_24")
    except Exception:
        import wave
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            pcm = np.clip(np.asarray(wav), -1.0, 1.0)
            pcm = (pcm * 32767).astype(np.int16)
            w.writeframes(pcm.tobytes())


def _stats(path: Path) -> tuple[float, float, float]:
    try:
        import soundfile as sf
        d, sr = sf.read(str(path))
        a = d if d.ndim == 1 else d.mean(axis=1)
        dur = len(a) / sr if sr else 0.0
        peak = float(np.max(np.abs(a))) if a.size else 0.0
        rms = float(np.sqrt(np.mean(a.astype(np.float64) ** 2))) if a.size else 0.0
        return dur, peak, rms
    except Exception:
        return 0.0, 0.0, 0.0


def _synth(engine, text: str, language: str, instruct: str | None,
           speaker=None) -> tuple[np.ndarray, int, float]:
    req = SynthesisRequest(text=text, language=language, speaker=speaker,
                           max_seconds_hint=180.0, speed=1.0,
                           instruct=instruct or None)
    t0 = time.perf_counter()
    res = engine.synthesize(req)
    return (np.asarray(res.waveform, dtype=np.float32).reshape(-1),
            int(res.sample_rate), time.perf_counter() - t0)


def main() -> int:
    hw = detect_hardware()
    if not getattr(hw, "cuda_available", False) and not getattr(hw, "gpu_name", ""):
        print("SKIP (keine CUDA-GPU): A/B-Hoertest nur auf dem GPU-Host "
              "ausfuehrbar.")
        return 0
    production = load_production()
    pron = PronunciationEngine()
    items: list[ABItem] = []

    voices = [(v, "German") for v in DE_VOICES] + [(v, "English") for v in EN_VOICES]
    for voice_id, language in voices:
        print(f"\n=== {voice_id} ({language}) ===")
        spec = JobSpec(voice_id=voice_id, text=".", language=language,
                       speed=1.0, formats="wav", output_mode="full")
        try:
            engine, entry = build_engine(spec, production)
            engine.load()
        except Exception as e:
            print(f"  SKIP (build/load fehlgeschlagen): {e}")
            continue
        vdir = OUT_DIR / voice_id
        vdir.mkdir(parents=True, exist_ok=True)

        # ---------------- Part A: Pacing ----------------
        for text_id, text in PACING_TEXTS[language]:
            norm = normalize_text(text, language, NormalizationReport())
            pacing = pacing_hint(language)
            variants = [
                ("V1_current", None, 1.0),
                ("V2_pacing", pacing, 1.0),
                ("V3_speed09", speed_instruct(0.9), 0.9),
            ]
            for label, instr, post in variants:
                item = ABItem(voice_id=voice_id, part="pacing", label=label,
                              text_id=text_id, original=text, tts_text=norm,
                              instruct=instr or "", post_speed=post,
                              language=language, speed=1.0)
                try:
                    wav, sr, elapsed = _synth(engine, norm, language, instr)
                    if abs(post - 1.0) >= 0.02:
                        wav, sr = apply_speed(wav, sr, post)
                    wpath = vdir / f"{text_id}_{label}.wav"
                    _write_wav(wpath, wav, sr)
                    dur, peak, rms = _stats(wpath)
                    item.wav = str(wpath)
                    item.duration_s, item.peak, item.rms = dur, peak, rms
                    item.elapsed_s = elapsed
                    item.ok = dur > 1.0 and rms > 0.002
                    print(f"  [{'OK' if item.ok else 'WEAK'}] {label:11s} "
                          f"{text_id}: {dur:6.1f}s  peak={peak:.3f} "
                          f"rms={rms:.4f}")
                except Exception as e:
                    item.error = f"{type(e).__name__}: {e}"
                    print(f"  [FAIL] {label} {text_id}: {item.error}")
                items.append(item)

        # ---------------- Part B: Mathematik ----------------
        if language == "German":
            for i, sent in enumerate(MATH_SENTENCES, 1):
                norm = normalize_text(sent, "German", NormalizationReport())
                m2 = pron.process(norm, "German", suggest_unknown=False)
                m1_text = apply_old_respellings(norm)
                for label, tts_text in (("M1_altrespell", m1_text),
                                        ("M2_neu_plain", m2.text)):
                    item = ABItem(voice_id=voice_id, part="math", label=label,
                                  text_id=f"math_{i:02d}", original=sent,
                                  tts_text=tts_text, instruct="",
                                  post_speed=1.0, language="German",
                                  speed=1.0)
                    try:
                        wav, sr, elapsed = _synth(engine, tts_text, "German",
                                                  None)
                        wpath = vdir / f"math_{i:02d}_{label}.wav"
                        _write_wav(wpath, wav, sr)
                        dur, peak, rms = _stats(wpath)
                        item.wav = str(wpath)
                        item.duration_s, item.peak, item.rms = dur, peak, rms
                        item.elapsed_s = elapsed
                        item.ok = dur > 1.0 and rms > 0.002
                        print(f"  [{'OK' if item.ok else 'WEAK'}] {label} "
                              f"{item.text_id}: {dur:5.1f}s  "
                              f"tts_text='{tts_text[:60]}...'")
                    except Exception as e:
                        item.error = f"{type(e).__name__}: {e}"
                        print(f"  [FAIL] {label} {item.text_id}: "
                              f"{item.error}")
                    items.append(item)
        try:
            engine.unload()
        except Exception:
            pass

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "audit.json").write_text(
        json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "items": [asdict(x) for x in items]},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")

    lines = ["# A/B Hoertest: Pacing (V1/V2/V3) + Mathematik (M1/M2)", "",
             "| Stimme | Teil | Label | Text | Dauer | TTS-Text (Anfang) | WAV |",
             "|---|---|---|---|---|---|---|"]
    for x in items:
        lines.append(
            f"| {x.voice_id} | {x.part} | {x.label} | {x.text_id} | "
            f"{x.duration_s:.1f}s | {x.tts_text[:50]} | "
            f"{Path(x.wav).name if x.wav else '-'} |")
    lines += ["", "Hinweis: V2_pacing = neuer Produktionspfad (speed=1.0, "
              "Erzeugung entspannter, KEIN Stretch). V3_speed09 nur als "
              "Referenz (alter 0.9-Stretch). M2_neu_plain = neuer "
              "Produktionspfad Mathematik.", ""]
    (OUT_DIR / "summary.md").write_text("\n".join(lines),
                                        encoding="utf-8")
    n_ok = sum(1 for x in items if x.ok)
    print(f"\nFERTIG: {n_ok}/{len(items)} Aufnahmen OK")
    print(f"Reports: {OUT_DIR / 'audit.json'} | {OUT_DIR / 'summary.md'}")
    return 0 if items else 1


if __name__ == "__main__":
    raise SystemExit(main())
