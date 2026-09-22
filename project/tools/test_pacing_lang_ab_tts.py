"""Sprachgetrennter Pacing-A/B-Hoertest (DE und EN SEPARAT).

Prueft die sprachspezifische Pausen-/Pacing-Trennung im echten
Produktionspfad und misst je Sprache:

  current : produktive Tabellen (german.py / english.py) unveraendert
  v2      : KANDIDAT-Werte, NUR im Speicher dieses Tools uebergeschrieben
            (Produktionsdateien bleiben byte-identisch; Hash-Nachweis im
            audit.json unter "production_files_unchanged")

Je Sprache und Variante werden gemessen/aufgezeichnet:
  - finaler Instruct je Segment (Produktionsfunktion build_instruct
    + sprachspezifischer Pacing-Hint)
  - komplette Pausezuweisung (Klasse + Sekunden je Segment)
  - WAV-Pfad, Audiodauer, WAV-SHA256, Dateigroesse
  - QC (Peak/RMS, nicht-stumm)

Laeuft NUR auf dem GPU-Host (echter Qwen-TTS); ohne CUDA sauberer SKIP.

Ausgabe: output/pacing_lang_ab/<lang>_<variant>.wav + audit.json + summary.md
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import types
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Headless-Tkinter-Stub
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
from app.hardware.detector import detect_hardware  # noqa: E402
from app.jobs.runner import JobSpec, build_engine  # noqa: E402
from app.prosody import english as EN_MOD  # noqa: E402
from app.prosody import german as DE_MOD  # noqa: E402
from app.prosody.instruct import build_instruct, pacing_hint  # noqa: E402
from app.prosody.pauses import assign_pauses  # noqa: E402
from app.security.identity_lock import load_production  # noqa: E402
from app.segmentation import SegmentationConfig, segment_text  # noqa: E402
from app.text.analyze import analyze_text  # noqa: E402
from app.tts.engine_base import SynthesisRequest  # noqa: E402
from app.voices.profiles import get_profile, profile_for_language  # noqa: E402

OUT_DIR = paths.OUTPUT_DIR / "pacing_lang_ab"

# Sprachgetrennte Konfiguration (STRIKT DE/EN getrennt):
LANG_CONFIG = {
    "German": {
        "module": DE_MOD,
        "tables": "DE (german.py: PAUSE_BASE_DE/PAUSE_STRATEGIES/..._DE)",
        "voice_id": "de_male_warm_storytelling_authoritative_01",
        "text": ("Die Entstehung des Weltalls, die Bildung der ersten "
                 "Sterne, das Werden der Galaxien vollzogen sich ueber "
                 "Zeitraeume, die sich jeder Vorstellung entziehen; was "
                 "bleibt, ist ein leises Staunen, das den Blick nach oben "
                 "lenkt. Es sind nicht die grossen Ereignisse, die "
                 "Geschichte machen, sondern die leisen Entscheidungen "
                 "vieler Menschen, die Tag fuer Tag, oft unbemerkt, die "
                 "Richtung veraendern, in der eine Gesellschaft sich "
                 "bewegt."),
    },
    "English": {
        "module": EN_MOD,
        "tables": "EN (english.py: PAUSE_BASE_EN/PAUSE_STRATEGIES_EN/..._EN)",
        "voice_id": "en_male_warm_storytelling_authoritative_02",
        "text": ("The mathematics, the physics, and the chemistry of the "
                 "natural world, along with careful observation, form the "
                 "foundation of modern science; it is not the great events "
                 "that shape history, but the quiet decisions of many "
                 "people, often unnoticed, that change the direction in "
                 "which a society is moving, and always will."),
    },
}

# KANDIDAT v2 - NUR fuer diesen Hoertest (Produktionswerte unveraendert).
V2_CANDIDATE = {
    "German": {
        "narrative": {"after_comma": 0.38, "after_semicolon": 0.62,
                      "after_colon": 0.66, "after_dash": 0.70,
                      "statement": 0.68, "paragraph": 1.55,
                      "chapter": 2.30, "end_of_text": 1.70},
        "limits": (0.22, 3.20),
    },
    "English": {
        "narrative": {"after_comma": 0.26, "after_semicolon": 0.58,
                      "after_colon": 0.60, "statement": 0.62,
                      "paragraph": 1.40, "chapter": 2.05,
                      "end_of_text": 1.55},
        "limits": (0.22, 3.00),
    },
}

SEG_CFG = SegmentationConfig(target_chars=220, min_chars=80, max_chars=420,
                             close_slack=0.45, hard_start_min_chars=100,
                             respect_paragraph_boundary=True)


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


PROJECT_ROOT = paths.ROOT


from contextlib import contextmanager  # noqa: E402


@contextmanager
def _v2_override(module, candidate: dict):
    """Kandidat v2 NUR im Speicher aktivieren; Restore garantiert."""
    backup_narr = dict(module.PAUSE_STRATEGIES_EN if hasattr(module, "PAUSE_STRATEGIES_EN")
                       else module.PAUSE_STRATEGIES)["narrative"]
    limits_key = ("PAUSE_LIMITS_EN" if hasattr(module, "PAUSE_LIMITS_EN")
                  else "PAUSE_LIMITS_DE")
    backup_limits = dict(getattr(module, limits_key))
    try:
        narr = (module.PAUSE_STRATEGIES_EN if hasattr(module, "PAUSE_STRATEGIES_EN")
                else module.PAUSE_STRATEGIES)
        narr["narrative"].update(candidate["narrative"])
        limits = dict(backup_limits)
        limits["narrative"] = candidate["limits"]
        setattr(module, limits_key, limits)
        yield
    finally:
        narr = (module.PAUSE_STRATEGIES_EN if hasattr(module, "PAUSE_STRATEGIES_EN")
                else module.PAUSE_STRATEGIES)
        narr["narrative"] = backup_narr
        setattr(module, limits_key, backup_limits)


@dataclass
class VariantResult:
    language: str
    variant: str          # current | v2
    tables: str
    voice_id: str
    wav: str = ""
    wav_sha256: str = ""
    wav_bytes: int = 0
    duration_s: float = 0.0
    pause_total_s: float = 0.0
    segments: int = 0
    pause_table: list = field(default_factory=list)   # [{type, s, text}]
    instructs: list = field(default_factory=list)
    qc_peak: float = 0.0
    qc_rms: float = 0.0
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


def _run_variant(engine, language: str, variant: str, vdir: Path) -> VariantResult:
    cfgm = LANG_CONFIG[language]
    res = VariantResult(language=language, variant=variant,
                        tables=cfgm["tables"], voice_id=cfgm["voice_id"])
    module = cfgm["module"]
    try:
        cm = (_v2_override(module, V2_CANDIDATE[language])
              if variant == "v2" else _noop())
        with cm:
            blocks = analyze_text(cfgm["text"]).blocks
            segs = segment_text(blocks, lambda b: b.text, SEG_CFG)
            assign_pauses(segs, style="relaxed", speed=1.0,
                          strategy="narrative", language=language)
            profile = get_profile(None)
            base_style = profile_for_language(profile, language)
            hint = pacing_hint(language)
            audio = []
            for seg in segs:
                instr = build_instruct(base_style, seg.text, language,
                                       emotion="AUTO", intensity="AUTO",
                                       profile_modifier="",
                                       long_sentence=(len(seg.text.split()) > 25))
                instr = instr + " " + hint
                res.instructs.append(instr)
                res.pause_table.append({"type": seg.pause_type,
                                        "s": seg.pause_after_s,
                                        "text": seg.text[:70]})
                r = engine.synthesize(SynthesisRequest(
                    text=seg.text, language=language, speaker=None,
                    max_seconds_hint=180.0, speed=1.0, instruct=instr))
                wav = np.asarray(r.waveform, dtype=np.float32).reshape(-1)
                audio.append((wav, int(r.sample_rate), seg))
            from app.audio.assemble import assemble_to_file
            wpath = vdir / f"{language}_{variant}.wav"
            sr, total_s, pause_s = assemble_to_file(audio, str(wpath))
            res.wav = str(wpath)
            res.wav_sha256 = _sha256_file(wpath)
            res.wav_bytes = wpath.stat().st_size
            res.duration_s = float(total_s)
            res.pause_total_s = float(pause_s)
            res.segments = len(segs)
            try:
                import soundfile as sf
                d, _ = sf.read(str(wpath))
                a = d if d.ndim == 1 else d.mean(axis=1)
                res.qc_peak = float(np.max(np.abs(a))) if a.size else 0.0
                res.qc_rms = float(np.sqrt(np.mean(a.astype(np.float64) ** 2))) if a.size else 0.0
            except Exception:
                pass
            res.ok = (res.duration_s > 3.0 and res.qc_rms > 0.002)
    except Exception as e:
        res.error = f"{type(e).__name__}: {e}"
    return res


def _noop():
    class _N:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
    return _N()


def main() -> int:
    hw = detect_hardware()
    if not getattr(hw, "cuda_available", False) and not getattr(hw, "gpu_name", ""):
        print("SKIP (keine CUDA-GPU): sprachgetrennter Pacing-A/B nur auf "
              "dem GPU-Host ausfuehrbar.")
        return 0
    production = load_production()
    prod_files = {name: _sha256_file(PROJECT_ROOT / name) for name in
                  ("app/prosody/german.py", "app/prosody/english.py")}
    results: list[VariantResult] = []

    # STRENG GETRENNT: erst ALLE DE-Varianten, dann ALLE EN-Varianten.
    for language in ("German", "English"):
        cfgm = LANG_CONFIG[language]
        print(f"\n================ {language} | Tabellen: {cfgm['tables']} "
              f"| Stimme: {cfgm['voice_id']} ================")
        spec = JobSpec(voice_id=cfgm["voice_id"], text=".",
                       language=language, speed=1.0, formats="wav",
                       output_mode="full")
        engine, entry = build_engine(spec, production)
        engine.load()
        vdir = OUT_DIR
        vdir.mkdir(parents=True, exist_ok=True)
        for variant in ("current", "v2"):
            r = _run_variant(engine, language, variant, vdir)
            results.append(r)
            state = "OK" if r.ok else ("FAIL" if r.error else "WEAK")
            print(f"  [{state}] {language}/{variant}: {r.duration_s:.1f}s "
                  f"(Pausen {r.pause_total_s:.2f}s, {r.segments} Segmente) "
                  f"sha={r.wav_sha256[:12]}")
            if r.error:
                print(f"         ! {r.error}")
            for row in r.pause_table:
                print(f"           [{row['type']:18s}] +{row['s']:.3f}s "
                      f"'{row['text']}...'")
        try:
            engine.unload()
        except Exception:
            pass

    after = {name: _sha256_file(PROJECT_ROOT / name) for name in prod_files}
    unchanged = prod_files == after

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "audit.json").write_text(json.dumps({
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "v2_candidate": V2_CANDIDATE,
        "production_files_unchanged": {"before": prod_files,
                                       "after": after,
                                       "unchanged": unchanged},
        "results": [asdict(r) for r in results],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# Sprachgetrennter Pacing-A/B (DE und EN separat)", "",
             f"Produktionsdateien unveraendert: "
             f"{'PASS' if unchanged else 'FAIL'}", "",
             "| Sprache | Variante | Segmente | Pausen | Dauer | WAV-SHA256 |",
             "|---|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r.language} | {r.variant} | {r.segments} | "
                     f"{r.pause_total_s:.2f}s | {r.duration_s:.1f}s | "
                     f"{r.wav_sha256[:16]} |")
    lines += ["", "Je Sprache getrennt vergleichen: current vs. v2 "
              "(DE-Entscheid unabhaengig von EN-Entscheid).", ""]
    (OUT_DIR / "summary.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"\nPRODUKTIONSDATEIEN UNVERAENDERT: "
          f"{'PASS' if unchanged else 'FAIL'}")
    print(f"FERTIG: {sum(1 for r in results if r.ok)}/{len(results)} Varianten OK")
    print(f"Reports: {OUT_DIR / 'audit.json'} | {OUT_DIR / 'summary.md'}")
    return 0 if results and unchanged else 1


if __name__ == "__main__":
    raise SystemExit(main())
