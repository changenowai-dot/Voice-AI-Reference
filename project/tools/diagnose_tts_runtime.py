#!/usr/bin/env python3
"""DIAGNOSE_TTS_RUNTIME — direkter TTS-Minimaltest ohne GUI.

Phasen 01–16 mit Start/Ende/Delta/Status. Keine endlosen "läuft..."-Meldungen.
Jeder Schritt hat einen harten Timeout (konfigurierbar, default 180 s pro
Phase für's ModelLoading, ansonsten kurz). Bei Fehler werden Exception und
vollständiger Traceback ausgegeben.

Beispiel:
    python project/tools/diagnose_tts_runtime.py ^
        --voice en_male_warm_storytelling_authoritative_02 --text "Hallo."
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import signal
import sys
import threading
import time
import traceback
import wave as _wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "project"))

# ---------------------------------------------------------------------------
# Hilfsstrukturen
# ---------------------------------------------------------------------------
@dataclass
class PhaseRec:
    name: str
    t_start: float = 0.0
    t_end: float = 0.0
    status: str = "pending"      # pending|running|ok|fail|skip|timeout
    detail: str = ""
    error: str = ""
    tb: str = ""

@dataclass
class Diag:
    voice_id: str
    text: str
    language: str
    phases: list[PhaseRec] = field(default_factory=list)
    output_wav: str | None = None
    dur_s: float | None = None
    sr: int | None = None
    ch: int | None = None
    sha256: str | None = None
    peak: float | None = None
    rms: float | None = None
    silent: bool | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def start(self, name: str) -> None:
        p = PhaseRec(name=name, t_start=time.time(), status="running")
        self.phases.append(p)
        _log(f"▶ [{name}] …")

    def ok(self, name: str, detail: str = "") -> None:
        p = self.phases[-1]
        p.t_end = time.time(); p.status = "ok"; p.detail = detail
        _log(f"  ✔ [{name}] OK ({p.t_end-p.t_start:.2f}s) {detail}")

    def fail(self, name: str, err: BaseException | str) -> None:
        p = self.phases[-1]
        p.t_end = time.time(); p.status = "fail"
        p.error = str(err)
        if isinstance(err, BaseException) and not isinstance(err, str):
            p.tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
        _log(f"  ✘ [{name}] FAIL ({p.t_end-p.t_start:.2f}s): {p.error}")
        if p.tb:
            _log("    --- Traceback ---")
            for line in p.tb.splitlines()[-12:]:
                _log("    " + line)

    def finalize(self, name: str, detail: str) -> None:
        self.start(name); self.ok(name, detail)


def _log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def _read_wav_meta(p: Path):
    """(sr, ch, frames, peak, rms, dur_s). Nutzt soundfile wenn verfügbar, sonst wave."""
    try:
        import soundfile as sf
        import numpy as np
        data, sr = sf.read(str(p), always_2d=False)
        ch = 1 if data.ndim == 1 else data.shape[1]
        n = int(data.shape[0])
        peak = float(abs(data).max()) if n > 0 else 0.0
        rms = float((data.astype("float64") ** 2).mean() ** 0.5) if n > 0 else 0.0
        return sr, ch, n, peak, rms
    except Exception:
        with _wave.open(str(p), "rb") as w:
            return w.getframerate(), w.getnchannels(), w.getnframes(), 0.0, 0.0


# ---------------------------------------------------------------------------
# Timeout-Helfer (thread-basiert, damit er auch unter Windows funktioniert;
# SIGALRM gibt es auf Windows nicht). Die Phase wird in einem Daemon-Thread
# ausgeführt; nach Timeout FAIL + Beenden des Gesamtprozesses (Exit 5).
# ---------------------------------------------------------------------------
class _PhaseTimeout(Exception):
    pass


def _run_with_timeout(timeout_s: float, label: str, fn, *a, **kw):
    """Rufe fn(*a,**kw) auf; breche nach timeout_s per Timeout-Fehler ab.

    Achtung: Einem festhängenden C/C++-Thread kann man unter Python/Windows
    nicht sauber von außen terminieren. Wir melden den Timeout
    UND beenden den Prozess hart via os._exit(5), weil sonst der
    Diagnoselauf ewig blockieren würde.
    """
    box: dict = {}
    def _target():
        try:
            box["result"] = fn(*a, **kw)
        except BaseException as e:
            box["error"] = e
    t = threading.Thread(target=_target, name=f"phase:{label}", daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        _log(f"  ⏹ [{label}] TIMEOUT nach {timeout_s}s – Phase hängt. "
             f"Beende Prozess hart (os._exit(5)), damit kein Deadlock bleibt.")
        os._exit(5)
    if "error" in box:
        raise box["error"]
    return box.get("result")


# ---------------------------------------------------------------------------
# Hauptdiagnose
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--voice", default="en_male_warm_storytelling_authoritative_02")
    ap.add_argument("--text", default="Hallo.")
    ap.add_argument("--language", default=None, choices=("German", "English"))
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--output-dir", default=None)
    ap.add_argument("--json", default=None)
    ap.add_argument("--phase-timeout", type=int, default=180,
                    help="Max. Sekunden pro Phase (default 180).")
    args = ap.parse_args()

    from app import paths
    paths.ensure_directories()

    language = args.language or ("English" if args.voice.startswith("en_") else "German")
    out_dir = Path(args.output_dir) if args.output_dir else (paths.OUTPUT_DIR / "diag")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_wav = out_dir / f"diag_{args.voice}_{language}.wav"
    if out_wav.exists():
        try: out_wav.unlink()
        except Exception: pass

    diag = Diag(voice_id=args.voice, text=args.text, language=language)
    T = args.phase_timeout
    t_all = time.time()

    # 01 environment
    diag.start("01_environment")
    try:
        import torch
        from app.hardware.detector import detect_hardware
        hw = detect_hardware()
        diag.meta.update({
            "torch_version": getattr(torch, "__version__", "?"),
            "cuda_available": bool(torch.cuda.is_available()),
            "cuda_version": torch.version.cuda or "",
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "",
            "hw_mode": hw.mode,
        })
        diag.ok("01_environment",
                f"torch={diag.meta['torch_version']} cuda={diag.meta['cuda_available']} "
                f"gpu={diag.meta['gpu'][:40]}")
    except Exception as e:
        diag.fail("01_environment", e); return _emit_final(diag, 2, args.json)

    # 02 voice resolution
    diag.start("02_voice_resolution")
    try:
        from app.voices.registry import VoiceRegistry
        reg = VoiceRegistry()
        entry = reg.get(args.voice)
        if entry is None:
            raise RuntimeError(f"Voice '{args.voice}' nicht in Registry")
        if entry.backend_mode != "clone":
            raise RuntimeError(f"Voice backend_mode={entry.backend_mode} (nur clone wird getestet)")
        diag.meta["display_name"] = entry.display_name
        diag.ok("02_voice_resolution", f"backend=clone display={entry.display_name}")
    except Exception as e:
        diag.fail("02_voice_resolution", e); return _emit_final(diag, 2, args.json)

    # 03 bundle resolution
    diag.start("03_bundle_resolution")
    try:
        from app.tts.reference_bundle import resolve_bundle
        bundle = resolve_bundle(args.voice, language=language,
                                require_manifest=(args.voice != "vd_e"),
                                auto_materialize=True)
        diag.meta["bundle_path"] = str(bundle.audio_path)
        diag.meta["bundle_sha"] = bundle.audio_sha256
        diag.ok("03_bundle_resolution", f"path={bundle.audio_path.name} sha={bundle.audio_sha256[:12]}")
    except Exception as e:
        diag.fail("03_bundle_resolution", e); return _emit_final(diag, 2, args.json)

    # 04 bundle validation
    diag.start("04_bundle_validation")
    try:
        ok, summary, detail = bundle.validate()
        if not ok:
            raise RuntimeError(summary)
        diag.meta.update({"bundle_sr": detail.get("sample_rate"),
                          "bundle_ch": detail.get("channels"),
                          "bundle_dur": detail.get("duration_s")})
        diag.ok("04_bundle_validation",
                f"sr={detail.get('sample_rate')} ch={detail.get('channels')} dur={detail.get('duration_s')}s")
    except Exception as e:
        diag.fail("04_bundle_validation", e); return _emit_final(diag, 2, args.json)

    # 05 model path resolution
    diag.start("05_model_path_resolution")
    model_path = None
    try:
        from app.tts.model_pool import QwenModelPool
        pool = QwenModelPool(hw)
        model_path = pool._resolve_model_path(pool.MODEL_REPOS["base"])
        from pathlib import Path as _P
        mp = _P(model_path)
        has_model = (mp/"model.safetensors").is_file() or any(mp.glob("*.safetensors"))
        has_cfg = (mp/"config.json").is_file()
        has_tok = ((mp/"tokenizer.json").is_file() or (mp/"tokenizer_config.json").is_file())
        if not has_model: raise RuntimeError(f"Keine Modelldatei in {model_path}")
        if not has_cfg:   raise RuntimeError(f"Keine config.json in {model_path}")
        if not has_tok:   raise RuntimeError(f"Keine Tokenizer-Datei in {model_path}")
        diag.ok("05_model_path_resolution", f"base={model_path}")
    except Exception as e:
        diag.fail("05_model_path_resolution", e); return _emit_final(diag, 3, args.json)

    # 06 tokenizer path resolution ist zusammen mit Model-Load in Qwen3TTSModel.from_pretrained
    # (Qwen lädt Tokenizer selbst). Wir dokumentieren den Pfad und machen ihn als separaten
    # Schritt sichtbar, indem wir die Tokenizer-Dateien prüfen.
    diag.start("06_tokenizer_path_resolution")
    try:
        mp = Path(model_path)
        tok_files = [p.name for p in mp.glob("tokenizer*")] + [p.name for p in mp.glob("*tokenizer*")]
        if not tok_files:
            raise RuntimeError(f"Keine tokenizer-Dateien in {model_path}")
        diag.ok("06_tokenizer_path_resolution", ", ".join(sorted(set(tok_files)))[:100])
    except Exception as e:
        diag.fail("06_tokenizer_path_resolution", e); return _emit_final(diag, 3, args.json)

    # 07/08 model+tokenizer initialization (zusammen, da from_pretrained beides tut)
    diag.start("07_model_initialization")
    diag.start("08_tokenizer_initialization")
    model = None
    try:
        def _init_model():
            return pool.get("base")   # lädt Model+Tokenizer
        t0 = time.time()
        model = _run_with_timeout(T, "07_model_initialization", _init_model)
        dt = time.time() - t0
        # Markiere beide Phasen als OK (Qwen3TTSModel.from_pretrained lädt
        # Tokenizer implizit mit).
        diag.phases[-2].t_end = time.time(); diag.phases[-2].status = "ok"
        diag.phases[-2].detail = f"from_pretrained OK ({dt:.1f}s)"
        diag.phases[-1].t_end = time.time(); diag.phases[-1].status = "ok"
        diag.phases[-1].detail = "Tokenizer implizit mitgeladen"
        _log(f"  ✔ [07_model_initialization] OK ({dt:.1f}s)")
        _log(f"  ✔ [08_tokenizer_initialization] OK")
        diag.meta["model_load_s"] = round(dt, 2)
    except Exception as e:
        diag.fail("07_model_initialization", e); return _emit_final(diag, 3, args.json)

    # 09 reference loading (Prompt erzeugen)
    diag.start("09_reference_loading")
    prompt = None
    try:
        from app.tts.voice_studio import QwenVoiceStudio
        studio = QwenVoiceStudio(pool)
        # _ensure_prompt Äquivalent: studio.build_clone_prompt
        from app.tts.voice_studio import VoiceRef
        ref = VoiceRef(candidate_id=args.voice, description="diag",
                       ref_text=bundle.reference_text, wav_path=bundle.audio_path,
                       language=language)
        t0 = time.time()
        def _build_prompt():
            return studio.build_clone_prompt(ref)
        prompt = _run_with_timeout(T, "09_reference_loading", _build_prompt)
        dt = time.time() - t0
        diag.ok("09_reference_loading", f"prompt built ({dt:.2f}s) key={prompt[1] if isinstance(prompt, tuple) else '?'}")
    except Exception as e:
        diag.fail("09_reference_loading", e); return _emit_final(diag, 3, args.json)

    # 10/11 generate
    diag.start("10_qwen_generate_start")
    diag.ok("10_qwen_generate_start", f"text={args.text!r} seed=None")
    diag.start("11_qwen_generate_end")
    result = None
    try:
        from app.tts.engine_base import SynthesisRequest
        req = SynthesisRequest(text=args.text, language=language,
                               speaker=args.voice, sampling={},
                               seed=None, max_seconds_hint=max(4.0, len(args.text)/12.0),
                               speed=args.speed)
        t0 = time.time()
        def _do_gen():
            return studio.synth_clone(prompt, req)
        result = _run_with_timeout(T, "11_qwen_generate_end", _do_gen)
        dt = time.time() - t0
        diag.ok("11_qwen_generate_end", f"dt={dt:.2f}s wav_len={len(result.waveform)} sr={result.sample_rate}")
        diag.meta["generate_s"] = round(dt, 2)
    except Exception as e:
        diag.fail("11_qwen_generate_end", e); return _emit_final(diag, 4, args.json)

    # 12 WAV write
    diag.start("12_wav_write")
    try:
        from app.audio.io import write_wav
        write_wav(out_wav, result.waveform, result.sample_rate, bit_depth=16)
        size = out_wav.stat().st_size
        if size < 44:
            raise RuntimeError(f"WAV zu klein: {size} bytes")
        diag.ok("12_wav_write", f"{out_wav} ({size} bytes)")
        diag.output_wav = str(out_wav)
    except Exception as e:
        diag.fail("12_wav_write", e); return _emit_final(diag, 4, args.json)

    # 13 WAV read-back
    diag.start("13_wav_readback")
    try:
        sr, ch, n, peak, rms = _read_wav_meta(out_wav)
        dur = n / float(max(1, sr))
        diag.sr = sr; diag.ch = ch; diag.dur_s = round(dur, 3)
        diag.peak = peak; diag.rms = rms
        diag.ok("13_wav_readback", f"sr={sr} ch={ch} frames={n} dur={dur:.2f}s")
    except Exception as e:
        diag.fail("13_wav_readback", e); return _emit_final(diag, 4, args.json)

    # 14 audio sanity
    diag.start("14_audio_sanity")
    try:
        if n == 0: raise RuntimeError("WAV hat 0 Frames")
        if sr < 8000 or sr > 48000: raise RuntimeError(f"Unübliche Samplerate {sr}")
        if dur < 0.3: raise RuntimeError(f"Audio zu kurz: {dur:.2f}s")
        if dur > 60:  raise RuntimeError(f"Audio zu lang: {dur:.2f}s")
        diag.ok("14_audio_sanity", "frames/samplerate/duration im plausiblen Bereich")
    except Exception as e:
        diag.fail("14_audio_sanity", e); return _emit_final(diag, 4, args.json)

    # 15 QC
    diag.start("15_qc")
    try:
        silent = (peak < 1e-4)
        diag.silent = silent
        if silent:
            raise RuntimeError(f"Audio ist still (peak={peak:.6f}, rms={rms:.6f})")
        diag.ok("15_qc", f"peak={peak:.4f} rms={rms:.4f} silent={silent}")
    except Exception as e:
        diag.fail("15_qc", e); return _emit_final(diag, 4, args.json)

    # SHA
    diag.sha256 = _sha256_file(out_wav)

    # 16 final result
    total = time.time() - t_all
    diag.finalize("16_final_result",
                  f"GESAMT={total:.2f}s wav={out_wav.name} sha={diag.sha256[:16]}…")

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(_diag_json(diag), encoding="utf-8")
        _log(f"JSON-Diagnose geschrieben: {args.json}")

    print()
    print("=" * 70)
    print(f"FINAL_DIAGNOSE=PASS ({total:.2f}s)")
    print(f"Output-WAV: {out_wav}")
    print(f"SHA256:     {diag.sha256}")
    print(f"Dauer:      {diag.dur_s}s  SR: {diag.sr}  CH: {diag.ch}")
    print("=" * 70)

    # VRAM aufzuräumen versuchen
    try:
        del model, studio, prompt, result
        gc.collect()
        import torch as _t
        if _t.cuda.is_available():
            _t.cuda.empty_cache(); _t.cuda.synchronize()
    except Exception:
        pass
    return 0


def _diag_json(diag: Diag) -> str:
    return json.dumps({
        "voice_id": diag.voice_id, "text": diag.text, "language": diag.language,
        "output_wav": diag.output_wav, "duration_s": diag.dur_s,
        "sample_rate": diag.sr, "channels": diag.ch,
        "sha256": diag.sha256, "peak": diag.peak, "rms": diag.rms,
        "silent": diag.silent,
        "meta": diag.meta,
        "phases": [{"name": p.name, "start": p.t_start, "end": p.t_end,
                    "delta_s": round(p.t_end - p.t_start, 3) if p.t_end else None,
                    "status": p.status, "detail": p.detail, "error": p.error}
                   for p in diag.phases],
    }, indent=2, ensure_ascii=False)


def _emit_final(diag: Diag, code: int, json_out: str | None = None) -> int:
    print()
    print("--- Phasen-Report ---")
    for p in diag.phases:
        if p.status == "ok":
            print(f"  ✔ {p.name}: {p.detail[:120]}")
        elif p.status == "fail":
            print(f"  ✘ {p.name}: {p.error[:200]}")
        elif p.status == "running":
            print(f"  ⏹ {p.name}: keine Antwort (möglicherweise Hänger vor dem Timeout)")
        else:
            print(f"  - {p.name}: {p.status}")
    print(f"\nFINAL_DIAGNOSE=FAIL (exit={code})")
    if json_out:
        try:
            Path(json_out).parent.mkdir(parents=True, exist_ok=True)
            Path(json_out).write_text(_diag_json(diag), encoding="utf-8")
            print(f"JSON-Diagnose (FAIL-Report): {json_out}")
        except Exception as e:
            print(f"(Konnte JSON-Report nicht schreiben: {e})")
    return code


if __name__ == "__main__":
    sys.exit(main())
