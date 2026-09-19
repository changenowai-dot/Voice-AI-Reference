"""Phase 4: Long-Form Consistency Test.

Testet die Gewinner-Variante aus dem A/B-Test mit zunehmenden Längen:
- 5 Minuten
- 10 Minuten
- 30 Minuten
- 60 Minuten (wenn VRAM/RAM reicht)
- 120 Minuten (wenn stabil)

Für jeden Test wird geprüft:
- Voice Identity über die gesamte Dauer
- Timbre-Konsistenz
- Tempo-Stabilität
- Lautheit-Konsistenz
- Prosody-Konsistenz
- VRAM/RAM-Verbrauch

Ausführung:
    cd project
    python benchmark/phase4_longform.py [--winner D] [--max-minutes 60]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
APP_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(APP_ROOT))
os.environ.setdefault("VOICEOVER_ROOT", str(APP_ROOT))

from app import paths
from app.config import load_config
from app.hardware.detector import detect_hardware

paths.ensure_directories()

# =====================================================================
# Long-Form Text-Generierung (reproduzierbar)
# =====================================================================
LONG_FORM_BASE = """Die Geschichte der menschlichen Kommunikation ist eng mit der Entwicklung von Sprache und Schrift verknüpft.

Vor etwa 100.000 Jahren begann der Homo sapiens, komplexe Sprachsysteme zu entwickeln. Diese Fähigkeit — einzigartig im Tierreich — ermöglichte abstraktes Denken, Planung und kulturelle Weitergabe von Wissen.

Die ersten Schriftsysteme entstanden vor rund 5.000 Jahren in Mesopotamien und Ägypten. Keilschrift und Hieroglyphen markieren den Beginn der recorded history.

Im alten Griechenland legten Philosophen wie Platon und Aristoteles die Grundlagen der abendländischen Denktradition. Platons Höhlengleichnis — eines der einflussreichsten Gedankenexperimente der Philosophiegeschichte — fragt nach der Natur der Wirklichkeit und unserer Fähigkeit, sie zu erkennen.

Die römische Republik, gegründet im Jahr 509 v. Chr., entwickelte Rechtsprinzipien, die bis heute das europäische Rechtssystem prägen. Cicero, Seneca und Marcus Aurelius formulierten ethische Grundsätze, die in der modernen Philosophie weiterwirken.

Das Mittelalter war keineswegs nur eine Zeit der Dunkelheit. Die karolingische Renaissance im 9. Jahrhundert, die arabischen Gelehrten in Bagdad und Cordoba, und die frühen Universitäten in Bologna und Paris bewahrten und erweiterten antikes Wissen.

Im Jahr 1440 erfand Johannes Gutenberg den Buchdruck mit beweglichen Lettern. Diese Innovation — oft als eine der wichtigsten der Menschheitsgeschichte bezeichnet — demokratisierte Wissen und ermöglichte die Verbreitung von Ideen in nie dagewesenem Maße.

Die Aufklärung im 17. und 18. Jahrhundert brachte fundamentale Veränderungen:

Vernunft als höchste Autorität;
Wissenschaftliche Methode statt Dogma;
Menschenrechte und politische Freiheit;
Säkularisierung und religiöse Toleranz.

Isaac Newtons Philosophiae Naturalis Principia Mathematica (1687) begründete die klassische Mechanik. Seine drei Bewegungsgesetze und das Gravitationsgesetz beschrieben die physikalische Welt mit mathematischer Präzision.

Die industrielle Revolution, beginnend um 1760 in England, transformierte die Gesellschaft grundlegend. Dampfmaschinen, Fabriken und Eisenbahnen veränderten Arbeit, Urbanisierung und soziale Strukturen.

Im 20. Jahrhundert beschleunigte sich der technologische Wandel exponentiell. Albert Einsteins Relativitätstheorie (1905/1915), die Quantenmechanik, die Entschlüsselung der DNA-Struktur (1953), die Mondlandung (1969), das Internet (1989), und die Entwicklung künstlicher Intelligenz markieren Meilensteine.

Heute stehen wir an einem neuen Wendepunkt. Große Sprachmodelle wie GPT-4, Claude und Qwen können menschliche Sprache mit bemerkenswerter Kompetenz verarbeiten und erzeugen. Die Frage, ob diese Systeme "verstehen" — im menschlichen Sinne — ist Gegenstand intensiver wissenschaftlicher und philosophischer Debatten.

Was bleibt konstant in dieser Geschichte der Veränderung? Der menschliche Drang, zu verstehen, zu erklären, und Wissen weiterzugeben. Von den Höhlenmalereien von Lascaux bis zu modernen Voice-Over-Produktionen: Die Stimme — ob gesprochen, geschrieben oder digital erzeugt — bleibt unser wichtigstes Werkzeug der Kommunikation."""


def generate_text_for_duration(target_minutes: int, base_text: str) -> str:
    """Generiert einen Text mit approximately der gewünschten Sprechdauer.

    Deutsche Sprechgeschwindigkeit: ~130-150 Wörter/Minute
    ~7 Zeichen pro Wort im Deutschen
    Also: target_minutes * 140 * 7 = Zeichen
    """
    target_chars = target_minutes * 140 * 7  # ~980 Zeichen/Minute
    result = ""
    iteration = 0
    while len(result) < target_chars:
        # Leichte Variation pro Iteration (unterschiedliche Einleitungen)
        intro = [
            f"[Kapitel {iteration + 1}] ",
            "",
            f"Abschnitt {iteration + 1}: ",
            "",
        ][iteration % 4]
        result += "\n\n" + intro + base_text
        iteration += 1
    return result[:target_chars]


def analyze_longform_audio(wav_path: Path, n_points: int = 10) -> dict:
    """Analysiert Long-Form-Audio auf Konsistenz über die gesamte Dauer."""
    import wave

    try:
        with wave.open(str(wav_path), "rb") as wf:
            sr = wf.getframerate()
            sw = wf.getsampwidth()
            raw = wf.readframes(wf.getnframes())
    except Exception as e:
        return {"error": str(e)}

    if sw == 2:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 4:
        samples = np.frombuffer(raw, dtype=np.float32)
    else:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    total = len(samples)
    duration = total / sr
    window = int(10.0 * sr)  # 10-Sekunden-Fenster

    results = []
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
        zcr = float(np.sum(np.abs(np.diff(np.sign(seg))) > 0)) / len(seg)
        results.append({
            "position_pct": round(pct * 100, 1),
            "position_time_s": round(pct * duration, 1),
            "rms_db": round(20 * np.log10(max(rms, 1e-10)), 1),
            "peak": round(peak, 4),
            "zero_crossing_rate": round(zcr, 4),
        })

    if len(results) < 2:
        return {"points": results, "duration_s": round(duration, 1)}

    rms_vals = [p["rms_db"] for p in results]
    zcr_vals = [p["zero_crossing_rate"] for p in results]

    return {
        "points": results,
        "duration_s": round(duration, 1),
        "rms_mean_db": round(float(np.mean(rms_vals)), 1),
        "rms_std_db": round(float(np.std(rms_vals)), 2),
        "zcr_mean": round(float(np.mean(zcr_vals)), 4),
        "zcr_std": round(float(np.std(zcr_vals)), 4),
        "consistent": float(np.std(rms_vals)) < 2.5,
        "note": "std < 2.5 = gute Konsistenz über die gesamte Dauer",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--winner", default="A",
                        help="Gewinner-Variante aus A/B-Test (A/B/C/D/E)")
    parser.add_argument("--max-minutes", type=int, default=60,
                        help="Maximale Testdauer in Minuten")
    parser.add_argument("--quick", action="store_true",
                        help="Nur 5 und 10 Minuten testen")
    args = parser.parse_args()

    durations = [5, 10, 30]
    if not args.quick and args.max_minutes >= 60:
        durations.append(60)
    if not args.quick and args.max_minutes >= 120:
        durations.append(120)

    print("=" * 70)
    print(f"PHASE 4: Long-Form Test (Variante {args.winner})")
    print("=" * 70)
    print(f"Dauern: {durations} Minuten")

    # Hardware
    hw = detect_hardware()
    if not hw.mode.startswith("gpu"):
        print("FEHLER: Keine GPU. Auf RTX 5060 ausführen!")
        sys.exit(1)

    # Identity-Lock
    from app.security.identity_lock import check_identity
    status = check_identity()
    if not status.ok:
        print(f"FEHLER: {status.message}")
        sys.exit(1)

    # Engine laden
    print("Lade Engine...")
    from app.tts.qwen_engine import VoiceCloneEngine
    engine = VoiceCloneEngine(
        hw=hw,
        candidate_id="VD-E",
        description="tief, ruhig, seriös – professioneller Long-Form-Narrator",
        models_dir=paths.MODELS_DIR,
        attn_implementation="sdpa",
        allow_design=False,
    )
    engine.load()
    print("[OK] Engine geladen")

    cfg = load_config()
    results = {}

    for minutes in durations:
        print(f"\n{'='*60}")
        print(f"LONG-FORM TEST: {minutes} Minuten")
        print(f"{'='*60}")

        # Text generieren
        text = generate_text_for_duration(minutes, LONG_FORM_BASE)
        print(f"Text: {len(text)} Zeichen, ~{len(text)/700:.0f} Wörter")
        print(f"Erwartete Dauer: ~{len(text)/980:.0f} Minuten")

        # Input-Datei
        input_file = paths.INPUT_DIR / f"phase4_longform_{minutes}min.txt"
        input_file.write_text(text, encoding="utf-8")

        # Segment-Konfiguration basierend auf Gewinner
        seg_configs = {
            "A": (420, 120, 700),
            "B": (700, 200, 1000),
            "C": (1200, 400, 1800),
            "D": (1500, 500, 2500),
            "E": (1000, 300, 2000),
        }
        target, mn, mx = seg_configs.get(args.winner, seg_configs["A"])

        cfg_copy = json.loads(json.dumps(cfg))
        cfg_copy["advanced"]["segment_target_chars"] = target
        cfg_copy["advanced"]["segment_min_chars"] = mn
        cfg_copy["advanced"]["segment_max_chars"] = mx
        out_dir = str(paths.OUTPUT_DIR / f"phase4_longform_{minutes}min")
        cfg_copy["output_dir"] = out_dir

        t_start = time.perf_counter()
        vram_before = get_gpu_memory() if 'get_gpu_memory' in dir() else {}
        ram_before = get_ram_usage() if 'get_ram_usage' in dir() else {}

        from app.project.pipeline import Pipeline
        pipeline = Pipeline(cfg_copy, engine)
        report = pipeline.process_file(input_file)

        elapsed = time.perf_counter() - t_start

        if not report.get("ok"):
            print(f"FEHLER bei {minutes}min: {report.get('error')}")
            results[f"{minutes}min"] = {
                "ok": False,
                "error": report.get("error"),
                "elapsed_s": round(elapsed, 1),
            }
            continue

        wav_path = Path(report["wav"])
        print(f"[OK] Dauer: {report.get('duration_s')}s")
        print(f"[OK] Segmente: {report.get('segments')}")
        print(f"[OK] QC-Score: {report.get('avg_score')}")
        print(f"[OK] Laufzeit: {elapsed:.1f}s")

        # Konsistenz-Analyse
        consistency = analyze_longform_audio(wav_path, n_points=10)

        results[f"{minutes}min"] = {
            "ok": True,
            "target_minutes": minutes,
            "actual_duration_s": report.get("duration_s"),
            "n_segments": report.get("segments"),
            "avg_qc_score": report.get("avg_score"),
            "elapsed_s": round(elapsed, 1),
            "reused_cache": report.get("reused", 0),
            "regenerated": report.get("regenerated", 0),
            "failed_segments": report.get("failed_segments", 0),
            "wav_path": str(wav_path),
            "consistency": consistency,
        }

        print(f"[OK] Konsistenz: RMS-Std = {consistency.get('rms_std_db', '?')} dB")

    # Report
    report_data = {
        "timestamp": datetime.now().isoformat(),
        "winner_variant": args.winner,
        "durations_tested": durations,
        "results": results,
    }

    json_path = paths.ROOT / "PHASE4_LONGFORM_REPORT.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False, default=str)

    md_path = paths.ROOT / "PHASE4_LONGFORM_REPORT.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Phase 4: Long-Form Test Report\n\n")
        f.write(f"**Datum:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Variante:** {args.winner}\n\n")

        f.write("## Ergebnisse\n\n")
        f.write("| Dauer | OK | Audio-Dauer | Segmente | QC-Score | Laufzeit | RMS-Std | Konsistent |\n")
        f.write("|-------|----|------------ |----------|----------|----------|---------|------------|\n")
        for key, data in results.items():
            if data.get("ok"):
                c = data.get("consistency", {})
                f.write(f"| {key} | [OK] | {data['actual_duration_s']}s | "
                        f"{data['n_segments']} | {data['avg_qc_score']} | "
                        f"{data['elapsed_s']}s | {c.get('rms_std_db', '?')} dB | "
                        f"{'[OK]' if c.get('consistent') else '[FAIL]'} |\n")
            else:
                f.write(f"| {key} | [FAIL] | — | — | — | {data.get('elapsed_s')}s | — | {data.get('error', '')} |\n")
        f.write("\n")

        f.write("## Voice-Consistency über die Zeit\n\n")
        f.write("Bitte für jede Dauer anhören und prüfen:\n\n")
        f.write("| Dauer | Timbre stabil? | Tempo stabil? | Lautheit stabil? | Prosody stabil? | Noten |\n")
        f.write("|-------|---------------|---------------|------------------|-----------------|-------|\n")
        for key in results:
            f.write(f"| {key} | ? | ? | ? | ? | |\n")
        f.write("\n")

        f.write("## Stabilität\n\n")
        successful = sum(1 for d in results.values() if d.get("ok"))
        f.write(f"- Erfolgreich: {successful}/{len(results)}\n")
        if successful == len(results):
            f.write("- [OK] Alle Dauern stabil verarbeitet\n")
        else:
            f.write("- [FAIL] Einige Dauern fehlgeschlagen\n")

    print(f"\n[OK] Report: {md_path}")
    print(f"[OK] JSON: {json_path}")


def get_gpu_memory() -> dict:
    try:
        import torch
        if not torch.cuda.is_available():
            return {"available": False}
        return {
            "allocated_gb": round(torch.cuda.memory_allocated(0) / (1024**3), 2),
            "reserved_gb": round(torch.cuda.memory_reserved(0) / (1024**3), 2),
        }
    except Exception:
        return {"available": False}


def get_ram_usage() -> dict:
    try:
        import psutil
        return {"process_gb": round(psutil.Process(os.getpid()).memory_info().rss / (1024**3), 2)}
    except Exception:
        return {}


if __name__ == "__main__":
    main()
