#!/usr/bin/env python3
"""Kontrollierter Produktionsnachweis (4–5 echte Segmente) auf dem RTX-5060.

Verwendet die UNVERÄNDERTE Produktions-Pipeline (Segmentierung + QC +
generate_with_qc + Final-Gate + Retry-Logik) mit den Produktionsparametern
des echten Long-Form, aber einem kurzen, gezielten Text, sodass ca. 4–5
Segmente entstehen.

Ausgabe unter project/reproduction/CONTROLLED_SHORT/<voice_id>/:
    control.wav
    control_report.json
    control_SUMMARY.md

Start auf dem RTX-5060-Host aus dem Projekt-Root:
    .venv\Scripts\python.exe tools\controlled_short_run.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

_THIS = Path(__file__).resolve()
_PROJECT = _THIS.parents[1]
_REPO = _THIS.parents[2]
for p in (str(_PROJECT), str(_REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from app import config as cfgmod, paths  # noqa: E402
from app.hardware.detector import detect_hardware  # noqa: E402
from app.logging_setup import setup_logging, get_logger  # noqa: E402
from app.project.pipeline import Pipeline  # noqa: E402
from app.tts.qwen_engine import VoiceCloneEngine  # noqa: E402
from app.tts.sampler import params_for_set  # noqa: E402
from app.ui.progress import ProgressReporter  # noqa: E402
from app.voices.registry import VoiceRegistry  # noqa: E402
from app.jobs.runner import _resolve_voice_native_language, _resolve_voice_seed  # noqa: E402

log = get_logger("controlled")


# Kurzer deutscher Text (~140 Wörter, 4–5 Segmente à ~300–500 Zeichen).
# Kein spezieller Trick – normale Dokumentationssprache wie im Long-Form.
CONTROL_TEXT_DE = (
    "Die Industrialisierung hat die Lebensverhältnisse in Europa nachhaltig "
    "verändert. Fabriken entstanden in den Tälern, Städte wuchsen rasch, und "
    "viele Menschen zogen vom Land in die neu entstehenden Ballungsgebiete. "
    "Dort veränderten sich Arbeit und Alltag grundlegend. Maschinen übernahmen "
    "zuvor handwerkliche Tätigkeiten, Eisenbahnen verbanden Regionen, die zuvor "
    "kaum miteinander verbunden waren. Die Geschwindigkeit des Wandels war für "
    "die Zeitgenossen beispiellos. Zugleich wuchsen soziale Fragen: Arbeitszeit, "
    "Löhne, Wohnverhältnisse und Bildung wurden zu zentralen Themen der "
    "öffentlichen Debatte. Am Ende dieser Entwicklung stand eine moderne "
    "Gesellschaft, die auf Technik, Handel und wissenschaftlichem Fortschritt "
    "beruhte – und zugleich nach neuen Formen des Zusammenhalts suchte."
)
CONTROL_TEXT_EN = (
    "The industrial age transformed daily life across Europe. Factories "
    "appeared in the valleys, cities expanded quickly, and many people moved "
    "from the countryside into the newly growing urban centres. Work and "
    "everyday routines changed profoundly. Machines took over tasks once done "
    "by hand, and railways connected regions that had previously been almost "
    "separate. The pace of change felt unprecedented to those who lived through "
    "it. At the same time, social questions moved to the centre of public life: "
    "working hours, wages, housing, and education became the subject of "
    "sustained debate. What emerged was a modern society built on technology, "
    "trade, and scientific progress while searching for new forms of cohesion."
)


def _sha(p: Path) -> str:
    if not p or not p.exists() or not p.is_file():
        return ""
    h = hashlib.sha256()
    try:
        with open(p, "rb") as f:
            for blk in iter(lambda: f.read(1 << 20), b""):
                h.update(blk)
        return h.hexdigest().upper()
    except OSError:
        return ""


def run(voice_id: str, out_root: Path, text_override: str | None = None):
    setup_logging()
    paths.ensure_directories()
    out_root.mkdir(parents=True, exist_ok=True)
    out_dir = out_root / voice_id
    out_dir.mkdir(parents=True, exist_ok=True)

    registry = VoiceRegistry()
    entry = registry.get(voice_id)
    if entry is None:
        raise SystemExit(f"Stimme {voice_id} nicht in Registry")

    language = _resolve_voice_native_language(registry, entry)
    seed = _resolve_voice_seed(registry, entry)
    text = text_override or (CONTROL_TEXT_DE if language.lower().startswith("ger")
                             else CONTROL_TEXT_EN)
    text_path = out_dir / "input.txt"
    text_path.write_text(text, encoding="utf-8")

    hw = detect_hardware()
    engine = VoiceCloneEngine(hw=hw, candidate_id=voice_id,
                             description=entry.description or voice_id,
                             language=language, seed=seed)
    t_load0 = time.perf_counter()
    engine.load()
    load_s = time.perf_counter() - t_load0

    sampling = params_for_set("balanced", {
        "do_sample": True, "temperature": 0.7,
        "top_k": 50, "top_p": 0.90, "repetition_penalty": 1.05,
    })
    cfg = {
        "language": language,
        "preset": "deep_documentary",
        "voice_profile": voice_id,
        "voice": {"id": voice_id, "speaker": voice_id, "production_seed": seed},
        "speed": 1.0,
        "output_dir": str(out_dir),
        "output_format": "wav",
        "wav_bit_depth": 16,
        "wav_sample_rate": 24000,
        "mp3_bitrate": "320k",
        "advanced": {
            "cache_enabled": False,         # --fresh Verhalten (echte Neusynthese)
            "segment_target_chars": 420,
            "segment_min_chars": 120,
            "segment_max_chars": 700,
            "qc_enabled": True,
            "qc_max_attempts": 3,
            "qc_min_score": 78,
            "target_lufs": -14.0,
            "true_peak_dbtp": -1.5,
            "attn_implementation": "sdpa",
            "longform_run_tag": "controlled-short",
        },
        "german": {
            "instruct_variant": "de_doc_native",
            "min_german_score": 75.0,
            "tech_germanization": True,
            "variation": {"enabled": None, "strength": "subtle"},
        },
    }

    progress = ProgressReporter()
    pipeline = Pipeline(cfg, engine, progress=progress)

    t0 = time.perf_counter()
    report = pipeline.process_file(text_path)
    elapsed = time.perf_counter() - t0
    engine.unload()

    wav_path = Path(report.get("wav") or "")
    wav_sha = _sha(wav_path)

    short_pattern = {
        "too_short", "duration_implausible", "noise_like", "silence",
        "no_voiced_speech", "dropout", "nan",
    }

    summary = {
        "voice_id": voice_id,
        "language": language,
        "production_seed": seed,
        "engine_load_s": round(load_s, 2),
        "elapsed_s": round(elapsed, 2),
        "ok": bool(report.get("ok")),
        "segments_planned": report.get("segments"),
        "segments_reused": report.get("reused"),
        "segments_regenerated": report.get("regenerated"),
        "segments_failed": report.get("failed_segments"),
        "duration_s": report.get("duration_s"),
        "avg_score": report.get("avg_score"),
        "wav": str(wav_path),
        "wav_sha256": wav_sha,
        "warnings": report.get("warnings", []),
        "error": report.get("error"),
    }
    (out_dir / "control_report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # Kurze menschenlesbare Zusammenfassung
    md = []
    md.append(f"# Controlled Short Run – {voice_id}\n")
    md.append(f"Sprache: {language}  |  Seed: {seed}")
    md.append(f"Geplante Segmente: {summary['segments_planned']}  |  "
              f"reused={summary['segments_reused']}  "
              f"regen={summary['segments_regenerated']}  "
              f"failed={summary['segments_failed']}")
    md.append(f"Dauer: {summary['duration_s']}s  |  Ø-Score: {summary['avg_score']}  "
              f"|  ok={summary['ok']}")
    md.append(f"WAV: `{summary['wav']}`  |  SHA256: `{wav_sha[:16]}...`")
    if summary["warnings"]:
        md.append("\n## Warnings\n")
        for w in summary["warnings"][:10]:
            md.append(f"- {w}")
    md.append("\n## 0.16s-/Silence-Pattern-Check\n")
    md.append(f"- reused: {summary['segments_reused']} (erwartet: 0, weil fresh)")
    md.append(f"- failed_segments: {summary['segments_failed']}")
    md.append("- Detaillierte Pro-Segment-Daten sind über die Pipeline-Logs "
              "und den Project-State verfügbar; das zentrale Kriterium ist: "
              "keine massenhaften 0.16s-/Silence-Ausgaben, mehrheitlich "
              "sprachliche Segmente, Final-Gate blockiert nicht systematisch.")
    (out_dir / "control_SUMMARY.md").write_text(
        "\n".join(md), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="de_female_warm_empathetic_01")
    ap.add_argument("--out", default=None)
    ap.add_argument("--text", default=None)
    args = ap.parse_args()
    out = Path(args.out) if args.out else _PROJECT / "reproduction" / "CONTROLLED_SHORT"
    run(args.voice, out, args.text)


if __name__ == "__main__":
    main()
