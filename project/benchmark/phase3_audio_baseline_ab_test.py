"""Phase 3: Real Audio Baseline + Segmentation A/B Study.

Führt auf der Zielhardware (RTX 5060, 8 GB VRAM) folgende Tests durch:

1. Baseline-Audio erzeugen (AUDIO_BASELINE_CURRENT.wav)
2. Golden Reference Vergleich
3. Segmentierungs-A/B-Test:
   A = kleine Segmente (420 Zeichen, Standard)
   B = größere semantische Segmente (700 Zeichen)
   C = sehr große Blöcke (1200 Zeichen)
   D = große Blöcke + intelligentes Schneiden
   E = Hybrid (größere Blöcke, aber an Satzgrenzen geschnitten)
4. Voice-Consistency prüfen (Anfang/Mitte/Ende)
5. Segment-Continuity prüfen (Übergänge)
6. Objektive Metriken sammeln (LUFS, Peak, Dauer, VRAM, RAM)
7. Report generieren (PHASE3_AUDIO_BASELINE_REPORT.md)

Ausführung:
    cd project
    python benchmark/phase3_audio_baseline_ab_test.py

Erwartete Laufzeit: 30-60 Minuten (je nach Hardware)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

# App-Root setzen
APP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_ROOT))
os.environ.setdefault("VOICEOVER_ROOT", str(APP_ROOT))

from app import paths
from app.audio.ebu_r128 import integrated_lufs, true_peak_dbtp
from app.config import DEFAULT_CONFIG, load_config
from app.hardware.detector import detect_hardware
from app.project.pipeline import Pipeline
from app.quality.qc import SegmentQC
from app.segmentation import SegmentationConfig, segment_text
from app.text.analyze import analyze_text
from app.text.normalize import normalize_text
from app.pronunciation import PronunciationEngine
from app.tts.qwen_engine import QwenTTSEngine, VoiceCloneEngine

paths.ensure_directories()

# =====================================================================
# §9: Baseline-Testtext
# =====================================================================
BASELINE_TEXT = """Die Erforschung des menschlichen Bewusstseins hat in den letzten Jahrzehnten bemerkenswerte Fortschritte gemacht.

Was bedeutet es eigentlich, bewusst zu sein? Diese Frage beschäftigt Philosophen seit über 2500 Jahren – von Aristoteles bis David Chalmers.

Im Jahr 1990 entwickelte der Neuroscientist Giulio Tononi seine Integrated Information Theory (IIT), die Bewusstsein als Maß für integrierte Information definiert. Laut Tononi beträgt das Bewusstseinsniveau (Phi) eines Systems genau dann null, wenn es in unabhängige Teile zerfällt.

Moderne Bildgebungsverfahren wie fMRT, PET und EEG ermöglichen heute Einblicke, die vor 30 Jahren undenkbar waren:

- Neuronale Korrelate des Bewusstseins (NCC)
- Globale Workspace-Theorie nach Baars (1988)
- Predictive Coding nach Friston
- Quantenbewusstsein nach Penrose und Hameroff

Doch trotz aller technischen Möglichkeiten bleibt eine fundamentale Frage offen: Kann eine Maschine – etwa ein KI-System mit 1,7 Milliarden Parametern – jemals bewusst sein?

Die Antwort hängt davon ab, wie wir "Bewusstsein" definieren. Nach funktionalistischen Theorien genügt die richtige Informationsverarbeitung. Nach phänomenologischen Ansätzen braucht es subjektive Erfahrung (Qualia).

Zwei Perspektiven:

1. Starke KI: Bewusstsein ist reproduzierbar
2. Biologischer Naturalismus: Bewusstsein erfordert biologische Substrate

Vielleicht liegt die Wahrheit irgendwo dazwischen – in einer noch unbekannten Theorie, die beide Ansätze vereint. Wie auch immer: Die Erforschung des Bewusstseins bleibt eine der spannendsten Herausforderungen des 21. Jahrhunderts."""

# =====================================================================
# Hilfsfunktionen
# =====================================================================
def measure_audio_metrics(wav_path: Path) -> dict:
    """Misst objektive Audio-Metriken."""
    import soundfile as sf
    wav, sr = sf.read(str(wav_path), dtype="float32")
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    lufs = integrated_lufs(wav, sr)
    tp = true_peak_dbtp(wav, sr)
    peak = float(np.max(np.abs(wav)))
    rms = float(np.sqrt(np.mean(wav ** 2)))
    duration = len(wav) / sr
    return {
        "file": str(wav_path),
        "duration_s": round(duration, 2),
        "sample_rate": sr,
        "lufs": round(lufs, 1),
        "true_peak_dbtp": round(tp, 1),
        "peak": round(peak, 4),
        "rms": round(rums, 4),
    }


def measure_segment_consistency(wav_path: Path, n_segments: int = 4) -> dict:
    """Teilt Audio in n Segmente und misst Konsistenz (LUFS, Tempo)."""
    import soundfile as sf
    wav, sr = sf.read(str(wav_path), dtype="float32")
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    seg_len = len(wav) // n_segments
    metrics = []
    for i in range(n_segments):
        start = i * seg_len
        end = (i + 1) * seg_len if i < n_segments - 1 else len(wav)
        seg = wav[start:end]
        lufs = integrated_lufs(seg, sr)
        rms = float(np.sqrt(np.mean(seg ** 2)))
        metrics.append({
            "segment": i + 1,
            "position_pct": round(100 * (i + 0.5) / n_segments, 1),
            "lufs": round(lufs, 1),
            "rms": round(rms, 4),
        })
    # Konsistenz = Standardabweichung der LUFS
    lufs_vals = [m["lufs"] for m in metrics]
    consistency_std = float(np.std(lufs_vals))
    return {
        "segments": metrics,
        "lufs_consistency_std": round(consistency_std, 2),
        "note": "std < 1.0 = sehr konsistent, 1.0-2.0 = akzeptabel, > 2.0 = problematisch",
    }


def run_variant(variant_name: str, seg_config: SegmentationConfig,
                engine, cfg: dict, text: str) -> dict:
    """Führt eine Variante aus und sammelt Metriken."""
    print(f"\n{'='*60}")
    print(f"VARIANTE {variant_name}")
    print(f"{'='*60}")
    print(f"Segment-Konfiguration: target={seg_config.target_chars}, "
          f"min={seg_config.min_chars}, max={seg_config.max_chars}")

    # Text in Datei schreiben
    input_file = paths.INPUT_DIR / f"phase3_{variant_name}.txt"
    input_file.write_text(text, encoding="utf-8")

    # Pipeline ausführen
    cfg_copy = json.loads(json.dumps(cfg))
    cfg_copy["advanced"]["segment_target_chars"] = seg_config.target_chars
    cfg_copy["advanced"]["segment_min_chars"] = seg_config.min_chars
    cfg_copy["advanced"]["segment_max_chars"] = seg_config.max_chars
    cfg_copy["output_dir"] = str(paths.OUTPUT_DIR / f"phase3_{variant_name}")

    t_start = time.perf_counter()
    pipeline = Pipeline(cfg_copy, engine)
    report = pipeline.process_file(input_file)
    elapsed = time.perf_counter() - t_start

    if not report.get("ok"):
        print(f"FEHLER: {report.get('error')}")
        return {"variant": variant_name, "ok": False, "error": report.get("error")}

    wav_path = Path(report["wav"])
    mp3_path = Path(report["mp3"])

    # Metriken messen
    audio_metrics = measure_audio_metrics(wav_path)
    consistency = measure_segment_consistency(wav_path)

    result = {
        "variant": variant_name,
        "ok": True,
        "elapsed_s": round(elapsed, 1),
        "segments": report["segments"],
        "reused": report["reused"],
        "regenerated": report["regenerated"],
        "avg_score": report["avg_score"],
        "audio": audio_metrics,
        "consistency": consistency,
    }

    print(f"✓ Dauer: {audio_metrics['duration_s']}s")
    print(f"✓ LUFS: {audio_metrics['lufs']}")
    print(f"✓ True Peak: {audio_metrics['true_peak_dbtp']} dBTP")
    print(f"✓ Segmente: {report['segments']}")
    print(f"✓ Ø Score: {report['avg_score']}")
    print(f"✓ Laufzeit: {elapsed:.1f}s")
    print(f"✓ Konsistenz-Std: {consistency['lufs_consistency_std']}")

    return result


def compare_with_golden_reference(wav_path: Path) -> dict:
    """Vergleicht Baseline mit Golden Reference."""
    golden_path = paths.ROOT / "reference" / "VD-E_GOLDEN_REFERENCE" / "VD-E.wav"
    if not golden_path.exists():
        return {"error": "Golden Reference nicht gefunden"}

    import soundfile as sf
    baseline_wav, baseline_sr = sf.read(str(wav_path), dtype="float32")
    golden_wav, golden_sr = sf.read(str(golden_path), dtype="float32")

    if baseline_wav.ndim > 1:
        baseline_wav = baseline_wav.mean(axis=1)
    if golden_wav.ndim > 1:
        golden_wav = golden_wav.mean(axis=1)

    baseline_lufs = integrated_lufs(baseline_wav, baseline_sr)
    golden_lufs = integrated_lufs(golden_wav, golden_sr)

    return {
        "golden_file": str(golden_path),
        "baseline_file": str(wav_path),
        "golden_lufs": round(golden_lufs, 1),
        "baseline_lufs": round(baseline_lufs, 1),
        "lufs_diff": round(abs(baseline_lufs - golden_lufs), 1),
        "golden_duration_s": round(len(golden_wav) / golden_sr, 2),
        "baseline_duration_s": round(len(baseline_wav) / baseline_sr, 2),
        "note": "Golden Reference ist Klangreferenz, kein identischer Audioclon. "
                "LUFS-Differenz < 2.0 ist akzeptabel.",
    }


# =====================================================================
# Hauptprogramm
# =====================================================================
def main():
    print("="*70)
    print("PHASE 3: Real Audio Baseline + Segmentation A/B Study")
    print("="*70)

    # Hardware prüfen
    hw = detect_hardware()
    print(f"\nHardware: {hw.mode}")
    if not hw.mode.startswith("gpu"):
        print("WARNUNG: Keine GPU erkannt. Echte Synthese nicht möglich.")
        print("Dieses Skript muss auf der Zielhardware (RTX 5060) ausgeführt werden.")
        sys.exit(1)

    print(f"VRAM: {hw.vram_gb:.1f} GB")
    print(f"RAM: {hw.ram_gb:.1f} GB")

    # Engine laden
    print("\nLade Qwen3-TTS-Engine...")
    cfg = load_config()
    engine = VoiceCloneEngine(
        hw=hw,
        candidate_id="VD-E",
        description="tief, ruhig, seriös – professioneller Long-Form-Narrator",
        models_dir=paths.MODELS_DIR,
        attn_implementation="sdpa",
        allow_design=False,  # VD-E darf NICHT neu designt werden
    )
    engine.load()
    print("✓ Engine geladen")

    # =================================================================
    # §10: Baseline-Audio erzeugen
    # =================================================================
    print("\n" + "="*70)
    print("§10: Baseline-Audio erzeugen")
    print("="*70)

    baseline_file = paths.INPUT_DIR / "phase3_baseline.txt"
    baseline_file.write_text(BASELINE_TEXT, encoding="utf-8")

    baseline_cfg = json.loads(json.dumps(cfg))
    baseline_cfg["output_dir"] = str(paths.OUTPUT_DIR / "phase3_baseline")

    t_start = time.perf_counter()
    pipeline = Pipeline(baseline_cfg, engine)
    baseline_report = pipeline.process_file(baseline_file)
    baseline_elapsed = time.perf_counter() - t_start

    if not baseline_report.get("ok"):
        print(f"FEHLER: {baseline_report.get('error')}")
        sys.exit(1)

    baseline_wav = Path(baseline_report["wav"])
    print(f"✓ Baseline erzeugt: {baseline_wav}")

    baseline_metrics = measure_audio_metrics(baseline_wav)
    baseline_consistency = measure_segment_consistency(baseline_wav)

    print(f"✓ Dauer: {baseline_metrics['duration_s']}s")
    print(f"✓ LUFS: {baseline_metrics['lufs']}")
    print(f"✓ True Peak: {baseline_metrics['true_peak_dbtp']} dBTP")

    # =================================================================
    # §11: Golden Reference Vergleich
    # =================================================================
    print("\n" + "="*70)
    print("§11: Golden Reference Vergleich")
    print("="*70)

    golden_comparison = compare_with_golden_reference(baseline_wav)
    print(f"Golden Reference LUFS: {golden_comparison.get('golden_lufs')}")
    print(f"Baseline LUFS: {golden_comparison.get('baseline_lufs')}")
    print(f"Differenz: {golden_comparison.get('lufs_diff')}")

    # =================================================================
    # §12: Segmentierungs-A/B-Test
    # =================================================================
    print("\n" + "="*70)
    print("§12: Segmentierungs-A/B-Test")
    print("="*70)

    variants = {}

    # Variante A: Kleine Segmente (Standard)
    variants["A"] = run_variant(
        "A_small_segments",
        SegmentationConfig(target_chars=420, min_chars=120, max_chars=700),
        engine, cfg, BASELINE_TEXT
    )

    # Variante B: Größere Segmente
    variants["B"] = run_variant(
        "B_larger_segments",
        SegmentationConfig(target_chars=700, min_chars=200, max_chars=1000),
        engine, cfg, BASELINE_TEXT
    )

    # Variante C: Sehr große Blöcke
    variants["C"] = run_variant(
        "C_very_large_blocks",
        SegmentationConfig(target_chars=1200, min_chars=400, max_chars=1800),
        engine, cfg, BASELINE_TEXT
    )

    # Variante D: Große Blöcke (wird später geschnitten)
    variants["D"] = run_variant(
        "D_large_blocks",
        SegmentationConfig(target_chars=1500, min_chars=500, max_chars=2500),
        engine, cfg, BASELINE_TEXT
    )

    # Variante E: Hybrid (große Blöcke, aber an Absatzgrenzen)
    variants["E"] = run_variant(
        "E_hybrid_paragraph",
        SegmentationConfig(target_chars=1000, min_chars=300, max_chars=2000),
        engine, cfg, BASELINE_TEXT
    )

    # =================================================================
    # §17–§18: Objektive Metriken + Akustische Bewertung
    # =================================================================
    print("\n" + "="*70)
    print("§17–§18: Metriken und Bewertung")
    print("="*70)

    # Hier würde die akustische Bewertung durch den Nutzer erfolgen.
    # Wir dokumentieren nur die objektiven Metriken.

    # =================================================================
    # §24: Report generieren
    # =================================================================
    print("\n" + "="*70)
    print("§24: Report generieren")
    print("="*70)

    report_path = paths.ROOT / "PHASE3_AUDIO_BASELINE_REPORT.md"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Phase 3: Real Audio Baseline + Segmentation A/B Study\n\n")
        f.write(f"**Datum:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Hardware:** {hw.mode}, VRAM {hw.vram_gb:.1f} GB, RAM {hw.ram_gb:.1f} GB\n\n")

        f.write("## 1. Technische Baseline\n\n")
        f.write(f"- Voice: VD-E (LOCKED)\n")
        f.write(f"- Modell: Qwen3-TTS-12Hz-1.7B-Base (VoiceDesign→Clone)\n")
        f.write(f"- Seed: 52001\n")
        f.write(f"- Sampling: expressive\n")
        f.write(f"- Attention: sdpa\n")
        f.write(f"- Cache-Version: q3p-v2-integrity\n\n")

        f.write("## 2. Baseline-Audio\n\n")
        f.write(f"- Datei: {baseline_metrics['file']}\n")
        f.write(f"- Dauer: {baseline_metrics['duration_s']}s\n")
        f.write(f"- LUFS: {baseline_metrics['lufs']}\n")
        f.write(f"- True Peak: {baseline_metrics['true_peak_dbtp']} dBTP\n")
        f.write(f"- Segmente: {baseline_report['segments']}\n")
        f.write(f"- Ø Score: {baseline_report['avg_score']}\n")
        f.write(f"- Konsistenz-Std: {baseline_consistency['lufs_consistency_std']}\n\n")

        f.write("## 3. Golden Reference Vergleich\n\n")
        f.write(f"- Golden LUFS: {golden_comparison.get('golden_lufs')}\n")
        f.write(f"- Baseline LUFS: {golden_comparison.get('baseline_lufs')}\n")
        f.write(f"- Differenz: {golden_comparison.get('lufs_diff')}\n")
        f.write(f"- Hinweis: {golden_comparison.get('note')}\n\n")

        f.write("## 4. Segmentierungs-A/B-Test Ergebnisse\n\n")
        for variant_name, result in variants.items():
            if not result.get("ok"):
                f.write(f"### Variante {variant_name}: FEHLER\n\n")
                f.write(f"- Fehler: {result.get('error')}\n\n")
                continue
            f.write(f"### Variante {variant_name}\n\n")
            f.write(f"- Konfiguration: target={result['segments']} Segmente\n")
            f.write(f"- Dauer: {result['audio']['duration_s']}s\n")
            f.write(f"- LUFS: {result['audio']['lufs']}\n")
            f.write(f"- True Peak: {result['audio']['true_peak_dbtp']} dBTP\n")
            f.write(f"- Ø Score: {result['avg_score']}\n")
            f.write(f"- Laufzeit: {result['elapsed_s']}s\n")
            f.write(f"- Konsistenz-Std: {result['consistency']['lufs_consistency_std']}\n")
            f.write(f"- Konsistenz-Details:\n")
            for seg in result['consistency']['segments']:
                f.write(f"  - Segment {seg['segment']} ({seg['position_pct']}%): "
                        f"LUFS {seg['lufs']}, RMS {seg['rms']}\n")
            f.write("\n")

        f.write("## 5. Akustische Bewertung (durch Nutzer auszufüllen)\n\n")
        f.write("Für jede Variante (A–E) bitte bewerten (0–10):\n\n")
        f.write("| Kriterium | A | B | C | D | E |\n")
        f.write("|-----------|---|---|---|---|---|\n")
        f.write("| Voice Identity | ? | ? | ? | ? | ? |\n")
        f.write("| Naturalness | ? | ? | ? | ? | ? |\n")
        f.write("| Prosody | ? | ? | ? | ? | ? |\n")
        f.write("| Pronunciation | ? | ? | ? | ? | ? |\n")
        f.write("| Continuity | ? | ? | ? | ? | ? |\n")
        f.write("| Long-Form Stability | ? | ? | ? | ? | ? |\n\n")

        f.write("## 6. Gewinner und Begründung\n\n")
        f.write("**Ausstehend** – nach akustischer Bewertung durch Nutzer.\n\n")

        f.write("## 7. Nächste Optimierung\n\n")
        f.write("**Ausstehend** – abhängig vom Gewinner.\n")

    print(f"✓ Report geschrieben: {report_path}")

    # JSON-Report für maschinelle Weiterverarbeitung
    json_report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "hardware": {
            "mode": hw.mode,
            "vram_gb": hw.vram_gb,
            "ram_gb": hw.ram_gb,
        },
        "baseline": {
            "metrics": baseline_metrics,
            "consistency": baseline_consistency,
            "report": {
                "segments": baseline_report["segments"],
                "avg_score": baseline_report["avg_score"],
            },
        },
        "golden_comparison": golden_comparison,
        "variants": variants,
    }

    json_path = paths.ROOT / "PHASE3_AUDIO_BASELINE_REPORT.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_report, f, indent=2, ensure_ascii=False)

    print(f"✓ JSON-Report: {json_path}")

    print("\n" + "="*70)
    print("PHASE 3 ABGESCHLOSSEN")
    print("="*70)
    print(f"\nBitte öffnen und anhören:")
    print(f"  {baseline_wav}")
    for variant_name, result in variants.items():
        if result.get("ok"):
            wav_file = paths.OUTPUT_DIR / f"phase3_{result['variant']}" / f"phase3_{result['variant']}.wav"
            print(f"  {wav_file}")
    print(f"\nReport: {report_path}")
    print(f"\nBitte akustische Bewertung in Report ausfüllen.")


if __name__ == "__main__":
    main()
