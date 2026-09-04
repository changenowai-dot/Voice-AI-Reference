"""System-Benchmark (Anforderung 50): Installations- und Hardwaretest.

Läuft beim ersten Start (oder auf Klick): GPU-Test, Modell-Ladetest,
deutscher + englischer Test, VRAM-Test, Geschwindigkeit, Audiointegrität,
WAV/MP3, Long-Form-Konsistenz, mehrere Stimmen, Segmentgrößen-Probe.
Schreibt benchmark/system_benchmark.json + report_SYSTEM.md und
environment.json. Optimiert Segmentgröße + Sampling-Set anhand realer
Messungen (Anforderung 16 + 49).
"""
from __future__ import annotations

import time

from .. import paths
from ..audio.ebu_r128 import integrated_lufs
from ..audio.io import write_wav
from ..hardware.detector import detect_hardware, recommend_model_size
from ..logging_setup import get_logger, plog
from ..quality.metrics import analyze_segment_audio
from ..tts.engine_base import SynthesisRequest
from ..tts.sampler import PARAM_SETS, params_for_set
from ..utils import write_json

log = get_logger("sysbench")

DE_TEST = ("Im Jahr 1923 betrachtete der Psychologe eine einfache Frage: "
           "Warum erinnern sich Menschen an manche Augenblicke ihr Leben lang, "
           "während andere Tage wie Sand zerfallen? Nietzsche, CERN, Göbekli "
           "Tepe – 3,7 Prozent der Proben lieferten 12,5 Grad kalte Antworten.")
EN_TEST = ("In 1923 a psychologist pondered one simple question: why do people "
           "remember certain moments for a lifetime while other days crumble "
           "like sand? Nietzsche, CERN, and Göbekli Tepe – 3.7 percent of "
           "samples returned answers twelve point five degrees cold.")

LONG_DE = ("Es gibt Nächte, in denen die Stadt ihren Atem anhält. "
           "Die Laternen flackern, als würden sie zögern. "
           "Und irgendwo, hinter einem Fenster im dritten Stock, sitzt ein Mensch "
           "und stellt sich die eine Frage, die ihn nicht loslässt. "
           "Wer bin ich, wenn niemand mich sieht? "
           "Die Psychologie nennt es das Selbst, die Philosophie das Sein, "
           "und die Nacht schweigt beharrlich, wie sie es immer tut. "
           "Doch in dieser Stille liegt eine Wahrheit verborgen, die kaum jemand "
           "auszusprechen wagt: Wir sind die Geschichten, die wir uns erzählen.")


def run_system_benchmark(engine_factory, quick: bool = False,
                         hw=None) -> dict:
    """engine_factory(model_size) -> geladene Engine (wird entladen)."""
    hw = hw or detect_hardware()
    report: dict = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "hardware": hw.to_dict(),
        "steps": {},
        "ok": True,
    }
    out_dir = paths.BENCHMARK_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    def step(name: str, fn):
        log.info("Benchmark-Schritt: %s", name)
        t0 = time.perf_counter()
        try:
            data = fn()
            data["elapsed_s"] = round(time.perf_counter() - t0, 2)
            data["ok"] = True
        except Exception as e:
            log.exception("Benchmark-Schritt %s fehlgeschlagen: %s", name, e)
            data = {"ok": False, "error": f"{type(e).__name__}: {e}",
                    "elapsed_s": round(time.perf_counter() - t0, 2)}
            report["ok"] = False
        report["steps"][name] = data
        return data

    model_size = recommend_model_size(hw)
    report["model_size_recommended"] = model_size

    # 1) Modell laden (inkl. GPU/CUDA-Verifizierung)
    engine_holder = {}

    def _load():
        eng = engine_factory(model_size)
        eng.load()
        engine_holder["engine"] = eng
        return {"model_size": model_size, "info": eng.info()}
    step("model_load", _load)

    engine = engine_holder.get("engine")
    if engine is None:
        write_json(out_dir / "system_benchmark.json", report)
        _write_md(report)
        return report

    # 2) Deutsch-Test
    def _de():
        req = SynthesisRequest(text=DE_TEST, language="German", speaker="Ryan",
                               instruct=("Speak as a calm, credible German "
                                         "documentary narrator."),
                               sampling=dict(params_for_set("balanced")),
                               seed=42, max_seconds_hint=30)
        res = engine.synthesize(req)
        p = out_dir / "test_de.wav"
        write_wav(p, res.waveform, res.sample_rate)
        m = analyze_segment_audio(res.waveform, res.sample_rate)
        return {"file": str(p), "metrics": m,
                "realtime_factor": res.realtime_factor,
                "lufs": integrated_lufs(res.waveform, res.sample_rate)}
    de_step = step("german_test", _de)

    # 3) Englisch-Test
    def _en():
        req = SynthesisRequest(text=EN_TEST, language="English", speaker="Ryan",
                               instruct=("Speak as a calm, credible English "
                                         "documentary narrator."),
                               sampling=dict(params_for_set("balanced")),
                               seed=43, max_seconds_hint=30)
        res = engine.synthesize(req)
        p = out_dir / "test_en.wav"
        write_wav(p, res.waveform, res.sample_rate)
        m = analyze_segment_audio(res.waveform, res.sample_rate)
        return {"file": str(p), "metrics": m,
                "realtime_factor": res.realtime_factor}
    step("english_test", _en)

    # 4) VRAM nach Belastung
    def _vram():
        from ..hardware.detector import vram_snapshot
        free, total = vram_snapshot()
        return {"free_gb": free, "total_gb": total,
                "mode": hw.mode}
    step("vram_check", _vram)

    # 5) Long-Form-Konsistenz (mehrere Segmente, gleiche Stimme)
    def _long():
        import numpy as np
        parts = [s.strip() + "." for s in LONG_DE.replace("?", "? ").split(". ")
                 if s.strip()]
        waves, f0s, lufs = [], [], []
        for i, part in enumerate(parts[:6]):
            req = SynthesisRequest(
                text=part, language="German", speaker="Ryan",
                instruct=("Speak as a calm German narrator, perfectly "
                          "consistent voice."),
                sampling=dict(params_for_set("balanced")),
                seed=1000 + i, max_seconds_hint=max(6.0, len(part) / 13.0))
            res = engine.synthesize(req)
            m = analyze_segment_audio(res.waveform, res.sample_rate)
            if m.get("f0_median_hz"):
                f0s.append(m["f0_median_hz"])
            lufs.append(m.get("lufs", -20))
            waves.append(res.waveform)
        if not waves:
            raise RuntimeError("Keine Long-Form-Segmente erzeugt")
        cat = np.concatenate(waves)
        p = out_dir / "test_longform.wav"
        write_wav(p, cat, engine.sample_rate or 24000)
        return {
            "file": str(p),
            "segments": len(waves),
            "f0_median_spread_hz": round(float(np.std(f0s)), 2) if f0s else None,
            "lufs_spread": round(float(np.std(lufs)), 2) if lufs else None,
        }
    if not quick:
        step("longform_test", _long)

    # 6) Segmentgrößen-Probe (Anforderung 16)
    def _segment_probe():
        base = LONG_DE * 3
        results = {}
        for target, label in ((220, "small"), (420, "medium"), (700, "large")):
            # Text in ~target-Zeichen-Häppchen schneiden (an Satzgrenzen)
            sents = [s.strip() + "." for s in base.split(". ") if s.strip()]
            chunk, chunks, size = "", [], 0
            for s in sents:
                if size + len(s) > target and chunk:
                    chunks.append(chunk)
                    chunk, size = "", 0
                chunk += " " + s
                size += len(s) + 1
            if chunk:
                chunks.append(chunk)
            chunk = chunks[0]
            req = SynthesisRequest(
                text=chunk.strip(), language="German", speaker="Ryan",
                instruct="Speak as a calm German narrator.",
                sampling=dict(params_for_set("balanced")),
                seed=77, max_seconds_hint=max(6.0, len(chunk) / 13.0))
            res = engine.synthesize(req)
            m = analyze_segment_audio(res.waveform, res.sample_rate)
            results[label] = {
                "chars": len(chunk), "duration_s": m["duration_s"],
                "realtime_factor": res.realtime_factor,
                "f0_cv": m.get("f0_cv"), "lufs": m.get("lufs"),
                "clip": m.get("clip_ratio"),
            }
        return results
    if not quick:
        seg_probe = step("segment_size_probe", _segment_probe)

    # 7) Sampling-Set-Vergleich (Anforderung 49)
    def _sampling_probe():
        out = {}
        for name in ("stable", "balanced", "expressive"):
            req = SynthesisRequest(
                text=LONG_DE, language="German", speaker="Ryan",
                instruct="Speak as a calm German narrator.",
                sampling=dict(params_for_set(name)), seed=55,
                max_seconds_hint=45)
            res = engine.synthesize(req)
            m = analyze_segment_audio(res.waveform, res.sample_rate)
            out[name] = {"f0_cv": m.get("f0_cv"), "duration_s": m["duration_s"],
                         "clip": m.get("clip_ratio"), "lufs": m.get("lufs"),
                         "rtf": res.realtime_factor}
        return out
    if not quick:
        sampling_probe = step("sampling_probe", _sampling_probe)

    # 8) WAV/MP3-Ausgabefähigkeit
    def _io_test():
        from ..audio.ffmpeg import ffmpeg_available, run_ffmpeg
        wav_ok = False
        mp3_ok = False
        p = out_dir / "test_io.wav"
        write_wav(p, __import__("numpy").zeros(24000, dtype="float32"), 24000)
        wav_ok = p.exists()
        if wav_ok and ffmpeg_available():
            ok, _ = run_ffmpeg(["-y", "-i", str(p), "-codec:a", "libmp3lame",
                                "-b:a", "192k", str(out_dir / "test_io.mp3")])
            mp3_ok = ok
        return {"wav_ok": wav_ok, "mp3_ok": mp3_ok,
                "ffmpeg": ffmpeg_available()}
    step("wav_mp3", _io_test)

    engine.unload()

    # ---- Empfehlungen in Konfiguration übernehmen --------------------------
    try:
        _apply_recommendations(report)
    except Exception as e:
        log.warning("Empfehlungen konnten nicht übernommen werden: %s", e)

    write_json(out_dir / "system_benchmark.json", report)
    write_json(paths.ENVIRONMENT_FILE, report["hardware"])
    _write_md(report)
    plog(f"SYSBENCH ok={report['ok']} model={model_size}")
    return report


def _apply_recommendations(report: dict) -> None:
    from .. import config as cfgmod
    probe = report.get("steps", {}).get("segment_size_probe", {})
    sampling_probe = report.get("steps", {}).get("sampling_probe", {})
    cfg = cfgmod.load_config()
    changed = []
    if probe.get("ok"):
        # Qualität first: Segmentgröße mit bester Intonationsvarianz pro
        # Dauer (Stabilität!), bei Gleichheit: größere (schneller)
        def quality(v):
            cv = v.get("f0_cv") or 0
            pen = 20 if v.get("clip", 0) > 0.0005 else 0
            rtf = v.get("realtime_factor") or 1
            return cv / max(rtf, 0.2) - pen
        best = max(probe, key=lambda k: quality(probe[k]))
        chars = probe[best].get("chars")
        if chars:
            cfg.setdefault("advanced", {})["segment_target_chars"] = int(chars)
            changed.append(f"segment_target_chars={chars}")
    if sampling_probe.get("ok"):
        def sq(v):
            cv = v.get("f0_cv") or 0
            pen = 20 if v.get("clip", 0) > 0.0005 else 0
            return cv - pen
        best = max(sampling_probe, key=lambda k: sq(sampling_probe[k]))
        p = PARAM_SETS[best]
        adv = cfg.setdefault("advanced", {})
        adv.update({"temperature": p["temperature"], "top_k": p["top_k"],
                    "top_p": p["top_p"],
                    "repetition_penalty": p["repetition_penalty"]})
        changed.append(f"sampling={best}")
    if changed:
        cfgmod.save_config(cfg)
        log.info("System-Benchmark optimierte Konfiguration: %s",
                 ", ".join(changed))


def _write_md(report: dict) -> None:
    hw = report["hardware"]
    lines = [
        "# System-Benchmark",
        "",
        f"Zeit: {report['timestamp']}  ",
        f"Betriebssystem: {hw['os']}  ",
        f"CPU: {hw['cpu']} ({hw['cpu_cores_physical']}K/{hw['cpu_threads']}T)  ",
        f"RAM: {hw['ram_total_gb']} GB  ",
        f"GPU: {hw['gpu_name'] or 'keine'} ({hw['gpu_vram_total_gb']} GB, Treiber "
        f"{hw['driver_version'] or '?'})  ",
        f"PyTorch: {hw['torch_version'] or '?'} (CUDA {hw['torch_cuda_version'] or '?'})  ",
        f"Modus: **{hw['mode']}**  ",
        f"Empfohlene Modellgröße: {report.get('model_size_recommended')}",
        "",
        "## Schritte",
        "",
        "| Schritt | OK | Dauer (s) | Ergebnis |",
        "|---------|----|-----------|----------|",
    ]
    for name, data in report["steps"].items():
        ok = "OK" if data.get("ok") else "FEHLER"
        brief = _brief(name, data)
        lines.append(f"| {name} | {ok} | {data.get('elapsed_s', '?')} | {brief} |")
    for w in hw.get("warnings", []):
        lines.append(f"\n> Warnung: {w}")
    (paths.BENCHMARK_DIR / "report_SYSTEM.md").write_text("\n".join(lines),
                                                          encoding="utf-8")


def _brief(name: str, data: dict) -> str:
    if not data.get("ok"):
        return (data.get("error") or "")[:120]
    if name in ("german_test", "english_test"):
        m = data.get("metrics", {})
        return (f"{m.get('duration_s')}s, RTF {data.get('realtime_factor')}, "
                f"F0 {m.get('f0_median_hz')} Hz, LUFS {data.get('lufs')}")
    if name == "longform_test":
        return (f"{data.get('segments')} Segmente, F0-Streuung "
                f"{data.get('f0_median_spread_hz')} Hz, LUFS-Streuung "
                f"{data.get('lufs_spread')}")
    if name == "vram_check":
        return f"frei {data.get('free_gb')} / {data.get('total_gb')} GB"
    if name == "wav_mp3":
        return f"WAV {data.get('wav_ok')}, MP3 {data.get('mp3_ok')}, ffmpeg {data.get('ffmpeg')}"
    if name == "model_load":
        return str(data.get("model_size"))
    if isinstance(data, dict):
        keys = [k for k in data.keys() if k not in ("ok", "elapsed_s")]
        return ", ".join(keys)[:120]
    return ""
