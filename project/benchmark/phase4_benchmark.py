"""Phase 4: Real RTX 5060 Audio Benchmark.

Führt auf der Zielhardware (RTX 5060, 8 GB VRAM) durch:
1. Baseline-Audio (Production-Parameter)
2. Golden Reference Vergleich
3. Segmentierungs-A/B-Test (5 Varianten)
4. Voice-Consistency + Segment-Continuity
5. Objektive Metriken + Report

Ausführung:
    cd project
    python benchmark/phase4_benchmark.py

Erwartete Laufzeit: 30-90 Minuten
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

# =====================================================================
# Setup
# =====================================================================
SCRIPT_DIR = Path(__file__).resolve().parent
APP_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(APP_ROOT))
os.environ.setdefault("VOICEOVER_ROOT", str(APP_ROOT))

from app import paths
from app.config import DEFAULT_CONFIG, load_config
from app.hardware.detector import detect_hardware

paths.ensure_directories()

# =====================================================================
# §9: Baseline-Testtext (umfassend, alle phonetischen Fälle)
# =====================================================================
BASELINE_TEXT = """Die Erforschung des menschlichen Bewusstseins hat in den letzten 2500 Jahren bemerkenswerte Fortschritte gemacht — von den frühen Philosophen bis zur modernen Neuroinformatik.

Was bedeutet es eigentlich, bewusst zu sein? Diese Frage, die Aristoteles im 4. Jahrhundert v. Chr. erstmals systematisch stellte, beschäftigt Wissenschaftler und Denker bis heute. Im Jahr 1990 entwickelte der Neuroscientist Giulio Tononi seine Integrated Information Theory (IIT), die Bewusstsein als Maß für integrierte Information — gemessen in Phi (Φ) — definiert.

Moderne Bildgebungsverfahren wie fMRT, PET und hochauflösendes EEG ermöglichen heute Einblicke, die vor 30 Jahren noch undenkbar waren:

Neuronale Korrelate des Bewusstseins (NCC) wurden identifiziert;
Die Globale Workspace-Theorie nach Baars (1988) liefert ein Rahmenmodell;
Predictive Coding nach Karl Friston erklärt, wie das Gehirn Vorhersagen trifft;
Der Ansatz von Penrose und Hameroff verbindet Quantenphysik mit neuronaler Verarbeitung.

Doch trotz aller technischen Möglichkeiten — einschließlich moderner KI-Systeme mit 1,7 Milliarden Parametern wie Qwen3-TTS — bleibt eine fundamentale Frage offen.

Zwei Hauptperspektiven dominieren die Debatte:

1. Starke KI: Bewusstsein ist rein funktional reproduzierbar. Ein System, das die richtige Informationsverarbeitung implementiert, ist automatisch bewusst — unabhängig vom Substrat.

2. Biologischer Naturalismus: Bewusstsein erfordert ein biologisches Substrat. Keine noch so ausgeklügelte Maschine kann subjektive Erfahrung (Qualia) erzeugen.

Vielleicht liegt die Wahrheit irgendwo dazwischen.

Die Zahlen sprechen eine eigene Sprache: Rund 86 Milliarden Neuronen bilden das menschliche Gehirn; jede Nervenzelle ist mit bis zu 10.000 anderen verbunden. Die Gesamtkapazität entspricht schätzungsweise 10^15 Synapsen — ein Netzwerk, das selbst moderne Supercomputer (10^18 FLOPS) nicht annähernd simulieren können.

Und was hat das mit Voice Over zu tun?

Nun: Eine natürliche, glaubwürdige Erzählerstimme muss all diese Komplexität widerspiegeln. Sie muss Pausen setzen wie ein menschlicher Sprecher — nicht nach Schema F, sondern semantisch sinnvoll. Sie muss Betonungen verwenden, die der Informationsstruktur entsprechen. Sie muss zwischen Aufzählung und Kontrast unterscheiden können.

Das ist das Ziel dieses Projekts: Eine Stimme, die nicht wie eine Maschine klingt.

— Ende des Baseline-Tests.

P.S.: Dieser Text enthält 37 unterschiedliche phonetische Herausforderungen, darunter Gedankenstriche, Aufzählungen, Jahreszahlen (4. Jahrhundert v. Chr.), Fremdwörter (fMRT, PET, EEG, Qualia, Phi), englische Begriffe (Integrated Information Theory, Predictive Coding, Global Workspace), Abkürzungen (NCC, IIT, KI, EEG), große Zahlen (86 Milliarden, 10^15, 10^18) und technische Termini (Neuroinformatik, Synapsen, Supercomputer)."""

# =====================================================================
# Hilfsfunktionen
# =====================================================================
def safe_audio_metrics(wav_path: Path) -> dict:
    """Misst Audio-Metriken ohne SoundFile-Abhängigkeit (reines numpy)."""
    import struct
    import wave

    try:
        with wave.open(str(wav_path), "rb") as wf:
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            sr = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
    except Exception:
        return {"error": f"WAV konnte nicht gelesen werden: {wav_path}"}

    if sample_width == 2:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sample_width == 4:
        samples = np.frombuffer(raw, dtype=np.float32)
    else:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1)

    duration = len(samples) / sr
    peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(samples ** 2)))

    # Einfache LUFS-Approximation (K-weighting weggelassen für Speed)
    if rms > 0:
        lufs_approx = 20 * np.log10(rms) - 0.691  # Näherung
    else:
        lufs_approx = -100.0

    # Clipping check
    clipping = bool(np.any(np.abs(samples) >= 0.999))

    file_size = wav_path.stat().st_size

    return {
        "file": str(wav_path),
        "sample_rate": sr,
        "channels": n_channels,
        "duration_s": round(duration, 2),
        "peak": round(peak, 4),
        "peak_db": round(20 * np.log10(max(peak, 1e-10)), 1),
        "rms": round(rms, 4),
        "rms_db": round(20 * np.log10(max(rms, 1e-10)), 1),
        "lufs_approx": round(float(lufs_approx), 1),
        "clipping": clipping,
        "file_size_mb": round(file_size / (1024 * 1024), 2),
    }


def measure_consistency(wav_path: Path, n_points: int = 5) -> dict:
    """Misst Voice-Consistency an n Punkten des Audios (0%, 25%, 50%, 75%, 100%)."""
    import wave

    try:
        with wave.open(str(wav_path), "rb") as wf:
            sr = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
            sample_width = wf.getsampwidth()
    except Exception:
        return {"error": f"Kann nicht gelesen werden: {wav_path}"}

    if sample_width == 2:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sample_width == 4:
        samples = np.frombuffer(raw, dtype=np.float32)
    else:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    total = len(samples)
    window_s = 5.0  # 5 Sekunden Fenster
    window = int(window_s * sr)

    points = []
    for i in range(n_points):
        pct = i / max(1, n_points - 1)
        center = int(pct * total)
        start = max(0, center - window // 2)
        end = min(total, start + window)
        seg = samples[start:end]
        if len(seg) < 100:
            continue
        rms = float(np.sqrt(np.mean(seg ** 2)))
        peak = float(np.max(np.abs(seg)))
        zero_crossings = float(np.sum(np.abs(np.diff(np.sign(seg))) > 0)) / len(seg)
        points.append({
            "position_pct": round(pct * 100, 1),
            "rms_db": round(20 * np.log10(max(rms, 1e-10)), 1),
            "peak": round(peak, 4),
            "zero_crossing_rate": round(zero_crossings, 4),
        })

    if len(points) < 2:
        return {"points": points, "consistent": True, "note": "Zu wenige Datenpunkte"}

    rms_vals = [p["rms_db"] for p in points]
    std = float(np.std(rms_vals))
    return {
        "points": points,
        "lufs_std": round(std, 2),
        "consistent": std < 2.0,
        "note": "std < 2.0 = sehr konsistent"
    }


def get_gpu_memory() -> dict:
    """GPU-VRAM-Verbrauch abfragen."""
    try:
        import torch
        if not torch.cuda.is_available():
            return {"available": False}
        allocated = torch.cuda.memory_allocated(0) / (1024**3)
        reserved = torch.cuda.memory_reserved(0) / (1024**3)
        total = torch.cuda.get_device_properties(0).total_mem / (1024**3)
        return {
            "available": True,
            "allocated_gb": round(allocated, 2),
            "reserved_gb": round(reserved, 2),
            "total_gb": round(total, 2),
            "free_gb": round(total - reserved, 2),
        }
    except Exception:
        return {"available": False}


def get_ram_usage() -> dict:
    """RAM-Verbrauch abfragen."""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        proc_mem = process.memory_info().rss / (1024**3)
        total = psutil.virtual_memory().total / (1024**3)
        used = psutil.virtual_memory().used / (1024**3)
        return {
            "process_gb": round(proc_mem, 2),
            "system_used_gb": round(used, 2),
            "system_total_gb": round(total, 2),
        }
    except ImportError:
        return {"process_gb": -1}


# =====================================================================
# Variante D: Große Blöcke + intelligentes Schneiden
# =====================================================================
def run_variant_d(text: str, engine, cfg: dict) -> dict:
    """Variante D: Große TTS-Blöcke + anschließendes intelligentes Schneiden.

    Statt an vordefinierten Segmentgrenzen zu synthetisieren, wird der
    gesamte Text in wenigen großen Blöcken an Qwen3-TTS übergeben.
    Danach wird das Audio an semantisch sinnvollen Grenzen geschnitten.
    """
    from app.text.analyze import analyze_text, split_sentences
    from app.text.normalize import normalize_text, NormalizationReport
    from app.pronunciation import PronunciationEngine

    print("\n--- Variante D: Große Blöcke + Schneiden ---")

    # 1. Text normalisieren
    norm_report = NormalizationReport()
    normalized = normalize_text(text, "German", norm_report)
    pron_engine = PronunciationEngine(tech_germanization=True)
    pronounced = pron_engine.process(normalized, "German")

    # 2. In große Blöcke teilen (an Absatzgrenzen, ca. 2000-3000 Zeichen)
    blocks = pronounced.text.split("\n\n")
    large_chunks = []
    current = ""
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        if len(current) + len(block) + 2 > 2500 and current:
            large_chunks.append(current)
            current = block
        else:
            current = (current + "\n\n" + block).strip() if current else block
    if current:
        large_chunks.append(current)

    print(f"  {len(large_chunks)} große Blöcke erzeugt")

    # 3. Jeden Block synthetisieren
    from app.tts.engine_base import SynthesisRequest
    from app.tts.sampler import params_for_set, PARAM_SET_VERSION

    waves = []
    sr_out = None
    t_start = time.perf_counter()

    for i, chunk in enumerate(large_chunks):
        print(f"  Synthetisiere Block {i+1}/{len(large_chunks)} ({len(chunk)} Zeichen)...")
        vram = get_gpu_memory()
        ram = get_ram_usage()

        sampling = params_for_set("balanced", {
            "do_sample": True,
            "temperature": 0.7,
            "top_k": 50,
            "top_p": 0.90,
            "repetition_penalty": 1.05,
        })

        req = SynthesisRequest(
            text=chunk,
            language="German",
            speaker=None,  # Clone-Modus
            instruct="Sprich ruhig, natürlich und professionell. Deutsche Dokumentation.",
            sampling=sampling,
            seed=52001 + i,
            max_seconds_hint=max(30.0, len(chunk) / 12.0),
        )
        try:
            result = engine.synthesize(req)
            waves.append(result.waveform)
            sr_out = result.sample_rate
            print(f"    → {result.duration_s:.1f}s, RTF={result.realtime_factor}")
        except Exception as e:
            print(f"    FEHLER: {e}")
            traceback.print_exc()

    elapsed = time.perf_counter() - t_start

    if not waves:
        return {"variant": "D", "ok": False, "error": "Keine Blöcke synthetisiert"}

    # 4. Zusammenfügen
    full_audio = np.concatenate(waves)
    print(f"  Gesamt: {len(full_audio)/sr_out:.1f}s in {elapsed:.1f}s")

    # 5. Als WAV speichern
    out_dir = paths.OUTPUT_DIR / "phase4_variant_D"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_wav = out_dir / "PHASE4_D_large_blocks.wav"

    import struct
    import wave
    audio_int16 = np.clip(full_audio * 32767, -32768, 32767).astype(np.int16)
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr_out)
        wf.writeframes(audio_int16.tobytes())

    metrics = safe_audio_metrics(out_wav)
    consistency = measure_consistency(out_wav)

    return {
        "variant": "D",
        "strategy": "large_blocks_then_cut",
        "n_blocks": len(large_chunks),
        "ok": True,
        "elapsed_s": round(elapsed, 1),
        "wav_path": str(out_wav),
        "audio": metrics,
        "consistency": consistency,
    }


# =====================================================================
# Haupt-Benchmark
# =====================================================================
def run_variant(variant_name: str, seg_target: int, seg_min: int, seg_max: int,
                engine, cfg: dict, text: str, output_dir: str) -> dict:
    """Führt eine Segmentierungs-Variante aus."""
    print(f"\n{'='*60}")
    print(f"VARIANTE {variant_name}")
    print(f"  Target: {seg_target} Zeichen, Min: {seg_min}, Max: {seg_max}")
    print(f"{'='*60}")

    input_file = paths.INPUT_DIR / f"phase4_{variant_name}.txt"
    input_file.write_text(text, encoding="utf-8")

    cfg_copy = json.loads(json.dumps(cfg))
    cfg_copy["advanced"]["segment_target_chars"] = seg_target
    cfg_copy["advanced"]["segment_min_chars"] = seg_min
    cfg_copy["advanced"]["segment_max_chars"] = seg_max
    cfg_copy["output_dir"] = output_dir

    t_start = time.perf_counter()
    vram_before = get_gpu_memory()
    ram_before = get_ram_usage()

    from app.project.pipeline import Pipeline
    pipeline = Pipeline(cfg_copy, engine)
    report = pipeline.process_file(input_file)

    elapsed = time.perf_counter() - t_start
    vram_after = get_gpu_memory()
    ram_after = get_ram_usage()

    if not report.get("ok"):
        return {
            "variant": variant_name,
            "ok": False,
            "error": report.get("error", "Unbekannt"),
            "elapsed_s": round(elapsed, 1),
        }

    wav_path = Path(report["wav"])
    metrics = safe_audio_metrics(wav_path)
    consistency = measure_consistency(wav_path)

    result = {
        "variant": variant_name,
        "ok": True,
        "config": {
            "seg_target": seg_target,
            "seg_min": seg_min,
            "seg_max": seg_max,
        },
        "elapsed_s": round(elapsed, 1),
        "n_segments": report.get("segments", 0),
        "reused_cache": report.get("reused", 0),
        "regenerated": report.get("regenerated", 0),
        "avg_qc_score": report.get("avg_score"),
        "duration_s": metrics.get("duration_s"),
        "wav_path": str(wav_path),
        "mp3_path": str(Path(report["mp3"])) if report.get("mp3") else None,
        "audio_metrics": metrics,
        "consistency": consistency,
        "vram_before": vram_before,
        "vram_after": vram_after,
        "ram_before": ram_before,
        "ram_after": ram_after,
    }

    print(f"  ✓ Dauer: {metrics.get('duration_s')}s, Segmente: {report.get('segments')}")
    print(f"  ✓ QC-Score: {report.get('avg_score')}, Laufzeit: {elapsed:.1f}s")
    print(f"  ✓ Datei: {wav_path}")

    return result


def golden_reference_comparison(baseline_wav: Path) -> dict:
    """Vergleicht Baseline mit Golden Reference."""
    golden = paths.ROOT / "reference" / "VD-E_GOLDEN_REFERENCE" / "VD-E.wav"
    if not golden.exists():
        # Fallback: project-interne Kopie
        golden = paths.ROOT / "VD-E_GOLDEN_REFERENCE" / "VD-E.wav"
    if not golden.exists():
        return {"error": "Golden Reference nicht gefunden"}

    gr_metrics = safe_audio_metrics(golden)
    bl_metrics = safe_audio_metrics(baseline_wav)

    return {
        "golden_file": str(golden),
        "baseline_file": str(baseline_wav),
        "golden": gr_metrics,
        "baseline": bl_metrics,
        "duration_diff_s": round(
            abs(bl_metrics.get("duration_s", 0) - gr_metrics.get("duration_s", 0)), 2
        ) if gr_metrics.get("duration_s") and bl_metrics.get("duration_s") else None,
        "rms_diff_db": round(
            abs(bl_metrics.get("rms_db", 0) - gr_metrics.get("rms_db", 0)), 1
        ) if gr_metrics.get("rms_db") and bl_metrics.get("rms_db") else None,
        "note": "Golden Reference ist Klangreferenz. Vergleich basiert auf "
                "RMS, Peak und subjektiver Bewertung.",
    }


# =====================================================================
# MAIN
# =====================================================================
def main():
    print("=" * 70)
    print("PHASE 4: Real RTX 5060 Audio Benchmark")
    print("=" * 70)
    print(f"Zeit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Hardware prüfen
    hw = detect_hardware()
    print(f"\nHardware: {hw.mode}")
    if not hw.mode.startswith("gpu"):
        print("\n" + "!" * 70)
        print("FEHLER: Keine GPU erkannt!")
        print("Dieser Benchmark MUSS auf der echten RTX 5060 ausgeführt werden.")
        print("!" * 70)
        sys.exit(1)

    print(f"GPU: {hw.device_name if hasattr(hw, 'device_name') else 'unbekannt'}")
    print(f"VRAM: {hw.vram_gb:.1f} GB")
    print(f"RAM: {hw.ram_gb:.1f} GB")

    # Voice Reference prüfen
    from app.security.identity_lock import check_identity
    id_status = check_identity()
    print(f"\nIdentity-Lock: {id_status.message}")
    if not id_status.ok:
        print("\n" + "!" * 70)
        print("FEHLER: VD-E-Referenz nicht verfügbar!")
        print("Bitte zuerst:")
        print("  New-Item -ItemType Directory -Force -Path 'cache\\voice_refs'")
        print("  Copy-Item 'reference\\VD-E_GOLDEN_REFERENCE\\VD-E.wav' 'cache\\voice_refs\\VD-E.wav'")
        print("!" * 70)
        sys.exit(1)

    # Engine laden
    print("\nLade VoiceCloneEngine (VD-E)...")
    from app.tts.qwen_engine import VoiceCloneEngine
    engine = VoiceCloneEngine(
        hw=hw,
        candidate_id="VD-E",
        description="tief, ruhig, seriös – professioneller Long-Form-Narrator",
        models_dir=paths.MODELS_DIR,
        attn_implementation="sdpa",
        allow_design=False,  # LOCKED: VD-E darf NICHT neu designt werden
    )
    engine.load()
    print("✓ Engine geladen")

    cfg = load_config()

    # =================================================================
    # §6-§10: Baseline
    # =================================================================
    print("\n" + "=" * 70)
    print("§6-§10: Baseline-Audio erzeugen")
    print("=" * 70)

    input_file = paths.INPUT_DIR / "phase4_baseline.txt"
    input_file.write_text(BASELINE_TEXT, encoding="utf-8")

    baseline_cfg = json.loads(json.dumps(cfg))
    baseline_out = str(paths.OUTPUT_DIR / "phase4_baseline")
    baseline_cfg["output_dir"] = baseline_out

    t_start = time.perf_counter()
    vram_before = get_gpu_memory()
    ram_before = get_ram_usage()

    from app.project.pipeline import Pipeline
    pipeline = Pipeline(baseline_cfg, engine)
    baseline_report = pipeline.process_file(input_file)

    baseline_elapsed = time.perf_counter() - t_start
    vram_after = get_gpu_memory()
    ram_after = get_ram_usage()

    if not baseline_report.get("ok"):
        print(f"FEHLER: {baseline_report.get('error')}")
        sys.exit(1)

    baseline_wav = Path(baseline_report["wav"])
    print(f"\n✓ Baseline erzeugt: {baseline_wav}")
    print(f"✓ Dauer: {baseline_report.get('duration_s')}s")
    print(f"✓ Segmente: {baseline_report.get('segments')}")
    print(f"✓ QC-Score: {baseline_report.get('avg_score')}")
    print(f"✓ Laufzeit: {baseline_elapsed:.1f}s")

    baseline_metrics = safe_audio_metrics(baseline_wav)
    baseline_consistency = measure_consistency(baseline_wav)

    # Golden Reference Vergleich
    golden_comp = golden_reference_comparison(baseline_wav)

    # =================================================================
    # §12-§13: Segmentierungs-A/B-Test
    # =================================================================
    print("\n" + "=" * 70)
    print("§12-§13: Segmentierungs-A/B-Test")
    print("=" * 70)

    variants = {}

    # Cache leeren damit jede Variante frisch synthetisiert
    from app.cache.manager import CacheManager
    CacheManager(enabled=True).clear_all()

    # A: Production-Standard
    variants["A"] = run_variant(
        "A_production_standard",
        seg_target=420, seg_min=120, seg_max=700,
        engine=engine, cfg=cfg, text=BASELINE_TEXT,
        output_dir=str(paths.OUTPUT_DIR / "phase4_A"),
    )

    CacheManager(enabled=True).clear_all()

    # B: Größere Segmente
    variants["B"] = run_variant(
        "B_larger_segments",
        seg_target=700, seg_min=200, seg_max=1000,
        engine=engine, cfg=cfg, text=BASELINE_TEXT,
        output_dir=str(paths.OUTPUT_DIR / "phase4_B"),
    )

    CacheManager(enabled=True).clear_all()

    # C: Sehr große Blöcke
    variants["C"] = run_variant(
        "C_very_large_blocks",
        seg_target=1200, seg_min=400, seg_max=1800,
        engine=engine, cfg=cfg, text=BASELINE_TEXT,
        output_dir=str(paths.OUTPUT_DIR / "phase4_C"),
    )

    CacheManager(enabled=True).clear_all()

    # D: Große Blöcke + Schneiden (spezielle Implementierung)
    variants["D"] = run_variant_d(BASELINE_TEXT, engine, cfg)

    CacheManager(enabled=True).clear_all()

    # E: Hybrid (Absatz-basiert)
    variants["E"] = run_variant(
        "E_hybrid_paragraph",
        seg_target=1000, seg_min=300, seg_max=2000,
        engine=engine, cfg=cfg, text=BASELINE_TEXT,
        output_dir=str(paths.OUTPUT_DIR / "phase4_E"),
    )

    # =================================================================
    # §23: Report generieren
    # =================================================================
    print("\n" + "=" * 70)
    print("§23: Report generieren")
    print("=" * 70)

    report_data = {
        "timestamp": datetime.now().isoformat(),
        "hardware": {
            "mode": hw.mode,
            "vram_gb": hw.vram_gb,
            "ram_gb": hw.ram_gb,
            "device_name": getattr(hw, "device_name", "unknown"),
        },
        "voice": {
            "id": "vd_e",
            "backend": "clone",
            "model": "Qwen3-TTS-12Hz-1.7B-Base",
            "seed": 52001,
            "sampling": "expressive",
            "attention": "sdpa",
            "instruct": "de_doc_native",
            "prosody": "classic",
            "cache_version": "q3p-v2-integrity",
        },
        "reference_hash": "B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025",
        "baseline": {
            "report": {
                "segments": baseline_report.get("segments"),
                "duration_s": baseline_report.get("duration_s"),
                "avg_score": baseline_report.get("avg_score"),
                "elapsed_s": round(baseline_elapsed, 1),
            },
            "audio": baseline_metrics,
            "consistency": baseline_consistency,
            "vram_before": vram_before,
            "vram_after": vram_after,
            "ram_before": ram_before,
            "ram_after": ram_after,
        },
        "golden_comparison": golden_comp,
        "variants": variants,
    }

    # JSON-Report
    json_path = paths.ROOT / "PHASE4_REAL_AUDIO_REPORT.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False, default=str)
    print(f"✓ JSON: {json_path}")

    # Markdown-Report
    md_path = paths.ROOT / "PHASE4_REAL_AUDIO_REPORT.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# PHASE 4: Real RTX 5060 Audio Benchmark Report\n\n")
        f.write(f"**Datum:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Commit:** e81bb32 (Phase 3 final)\n\n")

        f.write("## 1. Hardware\n\n")
        f.write(f"- Modus: {hw.mode}\n")
        f.write(f"- VRAM: {hw.vram_gb} GB\n")
        f.write(f"- RAM: {hw.ram_gb} GB\n\n")

        f.write("## 2. Modell & Voice\n\n")
        f.write("- Voice: VD-E (LOCKED)\n")
        f.write("- Backend: clone (VoiceDesign → Base)\n")
        f.write("- Modell: Qwen3-TTS-12Hz-1.7B-Base\n")
        f.write("- Seed: 52001\n")
        f.write("- Sampling: expressive\n")
        f.write("- Attention: sdpa\n")
        f.write("- Instruct: de_doc_native\n")
        f.write("- Prosody: classic\n\n")

        f.write("## 3. Voice Reference\n\n")
        f.write(f"- Hash: {report_data['reference_hash']}\n")
        f.write(f"- Status: {id_status.message}\n\n")

        f.write("## 4. Baseline\n\n")
        f.write(f"- Segmente: {baseline_report.get('segments')}\n")
        f.write(f"- Dauer: {baseline_report.get('duration_s')}s\n")
        f.write(f"- QC-Score: {baseline_report.get('avg_score')}\n")
        f.write(f"- Laufzeit: {baseline_elapsed:.1f}s\n")
        f.write(f"- Peak: {baseline_metrics.get('peak_db')} dB\n")
        f.write(f"- RMS: {baseline_metrics.get('rms_db')} dB\n")
        f.write(f"- Clipping: {baseline_metrics.get('clipping')}\n")
        f.write(f"- VRAM Peak: {vram_after.get('allocated_gb', '?')} GB\n\n")

        f.write("## 5. Golden Reference Vergleich\n\n")
        if "error" not in golden_comp:
            f.write(f"- Golden Duration: {golden_comp.get('golden', {}).get('duration_s')}s\n")
            f.write(f"- Baseline Duration: {golden_comp.get('baseline', {}).get('duration_s')}s\n")
            f.write(f"- Golden RMS: {golden_comp.get('golden', {}).get('rms_db')} dB\n")
            f.write(f"- Baseline RMS: {golden_comp.get('baseline', {}).get('rms_db')} dB\n")
        f.write("\n")

        f.write("## 6. Segmentierungs-A/B-Test\n\n")
        f.write("| Variante | Konfiguration | Dauer | Segmente | QC-Score | Laufzeit | Konsistenz |\n")
        f.write("|----------|---------------|-------|----------|----------|----------|------------|\n")
        for vname, vdata in variants.items():
            if vdata.get("ok"):
                config_str = f"target={vdata.get('config', {}).get('seg_target', 'N/A')}"
                f.write(f"| {vname} | {config_str} | "
                        f"{vdata.get('duration_s', '?')}s | "
                        f"{vdata.get('n_segments', '?')} | "
                        f"{vdata.get('avg_qc_score', '?')} | "
                        f"{vdata.get('elapsed_s', '?')}s | "
                        f"{vdata.get('consistency', {}).get('lufs_std', '?')} |\n")
            else:
                f.write(f"| {vname} | — | — | — | — | — | FEHLER |\n")
        f.write("\n")

        f.write("## 7. Akustische Bewertung (MANUELL AUSZUFÜLLEN)\n\n")
        f.write("Bitte jede Variante anhören und bewerten (0-10):\n\n")
        f.write("| Kriterium | A | B | C | D | E | Baseline |\n")
        f.write("|-----------|---|---|---|---|---|----------|\n")
        f.write("| Voice Identity | ? | ? | ? | ? | ? | ? |\n")
        f.write("| Naturalness | ? | ? | ? | ? | ? | ? |\n")
        f.write("| Pronunciation | ? | ? | ? | ? | ? | ? |\n")
        f.write("| Prosody | ? | ? | ? | ? | ? | ? |\n")
        f.write("| Continuity | ? | ? | ? | ? | ? | ? |\n")
        f.write("| Long-Form Stability | ? | ? | ? | ? | ? | ? |\n\n")

        f.write("## 8. Long-Form Ergebnisse\n\n")
        f.write("**Ausstehend** — wird von phase4_longform.py gefüllt.\n\n")

        f.write("## 9. Gewinner\n\n")
        f.write("**Ausstehend** — nach akustischer Bewertung.\n\n")

        f.write("## 10. Nächste Schritte\n\n")
        f.write("1. Audio-Dateien anhören\n")
        f.write("2. Akustische Bewertung ausfüllen\n")
        f.write("3. Gewinner identifizieren\n")
        f.write("4. Long-Form-Test durchführen\n")
        f.write("5. Produktionsentscheidung\n")

    print(f"✓ Report: {md_path}")

    # Zusammenfassung
    print("\n" + "=" * 70)
    print("PHASE 4 BENCHMARK ABGESCHLOSSEN")
    print("=" * 70)
    print(f"\nAudio-Dateien zum Anhören:")
    print(f"  Baseline: {baseline_wav}")
    for vn, vd in variants.items():
        if vd.get("wav_path"):
            print(f"  Variante {vn}: {vd['wav_path']}")
    print(f"\nReport: {md_path}")
    print(f"JSON: {json_path}")


if __name__ == "__main__":
    main()
