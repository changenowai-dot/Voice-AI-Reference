"""Batch-Verarbeitung (Anforderung 32, 33, 35).

Verarbeitet alle Textdateien im input/-Ordner nacheinander (sequenziell =
stabil und ressourcenschonend). Fehler einer Datei isolieren und
blockieren die übrigen nicht. Am Ende entsteht ein Bericht.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from .. import paths
from ..logging_setup import get_logger
from ..utils import write_json

log = get_logger("batch")

SUPPORTED_EXTENSIONS = (".txt",)


def natural_key(p: Path) -> list:
    parts = re.split(r"(\d+)", p.stem)
    return [int(s) if s.isdigit() else s.lower() for s in parts]


def list_input_files(input_dir: Path | None = None) -> list[Path]:
    d = Path(input_dir) if input_dir else paths.INPUT_DIR
    if not d.exists():
        return []
    files = [f for f in d.iterdir()
             if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
             and not f.name.startswith(".")]
    return sorted(files, key=natural_key)


class BatchRunner:
    def __init__(self, pipeline_factory, progress=None):
        """pipeline_factory() -> Pipeline (frisch pro Batch, Engine wird
        wiederverwendet)."""
        self.pipeline_factory = pipeline_factory
        self.progress = progress

    def run(self, files: list[Path] | None = None) -> dict:
        files = list_input_files() if files is None else [Path(f) for f in files]
        results: list[dict] = []
        n = len(files)
        t0 = time.perf_counter()
        if self.progress:
            self.progress.update(files_total=n, files_done=0, running=True,
                                 files=[], overall_percent=0)
        pipeline = self.pipeline_factory()

        for i, f in enumerate(files):
            if (self.progress is not None
                    and getattr(self.progress, "should_cancel", None)
                    and self.progress.should_cancel()):
                log.info("Batch nach Benutzer-Abbruch beendet (Datei %d/%d).", i, n)
                break
            if self.progress:
                self.progress.update(
                    current_file=f.name, file_index=i + 1, files_total=n,
                    files_done=i, current_segment=0, total_segments=0,
                    tts_percent=0, qc_percent=0, phase="tts")
            log.info("=== Datei %d/%d: %s ===", i + 1, n, f.name)
            try:
                rep = pipeline.process_file(f)
                rep["status"] = "ok" if rep.get("ok") else "failed"
            except Exception as e:                          # Fehlerisolierung
                log.exception("Datei %s komplett fehlgeschlagen: %s", f.name, e)
                rep = {"file": f.name, "ok": False, "status": "failed",
                       "error": f"{type(e).__name__}: {e}"}
            results.append(rep)
            if self.progress:
                self.progress.update(files_done=i + 1,
                                     overall_percent=int((i + 1) / n * 100))

        completed = sum(1 for r in results if r.get("ok"))
        failed = n - completed
        summary = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "files_total": n,
            "completed": completed,
            "failed": failed,
            "elapsed_s": round(time.perf_counter() - t0, 1),
            "results": results,
        }
        report_path = _write_report(summary)
        summary["report"] = str(report_path)
        if self.progress:
            self.progress.update(running=False, overall_percent=100,
                                 current_file=None, phase="done")
        log.info("Batch fertig: %d ok, %d fehlgeschlagen, Bericht: %s",
                 completed, failed, report_path)
        return summary


def _write_report(summary: dict) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = paths.OUTPUT_DIR / f"report_{stamp}.json"
    md_path = paths.OUTPUT_DIR / f"report_{stamp}.md"
    write_json(json_path, summary)
    lines = [
        "# VoiceOverApp – Batch-Bericht",
        "",
        f"Zeit: {summary['timestamp']}",
        f"Dateien gesamt: {summary['files_total']}",
        f"Abgeschlossen: {summary['completed']}",
        f"Fehlgeschlagen: {summary['failed']}",
        f"Dauer: {summary['elapsed_s']} s",
        "",
        "| # | Datei | Status | Segmente | Wiederverwendet | Score | Dauer |",
        "|---|-------|--------|----------|-----------------|-------|-------|",
    ]
    for i, r in enumerate(summary["results"], 1):
        status = "OK" if r.get("ok") else "FEHLER"
        lines.append(
            f"| {i} | {r.get('file', '?')} | {status} "
            f"| {r.get('segments', '-')} | {r.get('reused', '-')} "
            f"| {r.get('avg_score', '-')} | {r.get('duration_s', '-')} s |")
        if not r.get("ok") and r.get("error"):
            lines.append(f"  - Fehler: `{r['error']}`")
        for w in r.get("warnings", [])[:3]:
            lines.append(f"  - Warnung: {w}")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path
