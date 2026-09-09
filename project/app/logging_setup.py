"""Logging-Setup: application.log, errors.log, quality.log, performance.log.

Privatsphäre: Die Helper `short_text` kürzen Textinhalte auf Metadaten
(Länge + Hash), sofern log_text_content nicht explizit aktiviert ist
(Anforderung 68).
"""
from __future__ import annotations

import hashlib
import logging
import logging.handlers
import time
from pathlib import Path

from . import paths

FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-22s | %(message)s"
DATEFMT = "%Y-%m-%d %H:%M:%S"

_loggers: dict[str, logging.Logger] = {}
_configured = False


def _make_handler(logfile: str, level: int = logging.INFO) -> logging.handlers.RotatingFileHandler:
    path = paths.LOGS_DIR / logfile
    path.parent.mkdir(parents=True, exist_ok=True)
    h = logging.handlers.RotatingFileHandler(
        path, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    h.setLevel(level)
    h.setFormatter(logging.Formatter(FORMAT, datefmt=DATEFMT))
    return h


def setup_logging(log_text_content: bool = False, console: bool = True) -> None:
    global _configured, _log_text
    if _configured:
        _log_text = log_text_content
        return
    _configured = True
    paths.ensure_directories()

    root = logging.getLogger("voiceover")
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    app_h = _make_handler("application.log", logging.DEBUG)
    err_h = _make_handler("errors.log", logging.ERROR)
    qual_h = _make_handler("quality.log", logging.INFO)
    perf_h = _make_handler("performance.log", logging.INFO)
    qual_h.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt=DATEFMT))
    perf_h.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt=DATEFMT))

    # quality/performance nur über dedizierte Logger
    logging.getLogger("voiceover.quality").addHandler(qual_h)
    logging.getLogger("voiceover.performance").addHandler(perf_h)

    root.addHandler(app_h)
    root.addHandler(err_h)
    if console:
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter(FORMAT, datefmt=DATEFMT))
        root.addHandler(ch)

    _log_text = log_text_content


_log_text = False


def get_logger(name: str) -> logging.Logger:
    """Logger unter voiceover.*"""
    if not name.startswith("voiceover"):
        name = f"voiceover.{name}"
    return logging.getLogger(name)


def qlog(msg: str) -> None:
    get_logger("quality").info(msg)


def plog(msg: str) -> None:
    get_logger("performance").info(msg)


def text_fingerprint(text: str, max_len: int = 40) -> str:
    """Datenschutzfreundlicher Textfingerabdruck für Logs."""
    if _log_text:
        return repr(text[:200])
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]
    return f"<len={len(text)} sha={h} {repr(text[:max_len]) if False else ''}>".replace("  ", " ")


def safe_preview(text: str, max_len: int = 60) -> str:
    """Kurze Vorschau (nur Anfang, gekürzt) – für UI/Logs akzeptabel."""
    t = " ".join(text.split())
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


class Timer:
    """Kontextmanager für Performance-Logs."""

    def __init__(self, label: str):
        self.label = label
        self.t0 = 0.0
        self.elapsed = 0.0

    def __enter__(self) -> "Timer":
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc) -> None:
        self.elapsed = time.perf_counter() - self.t0
        plog(f"TIMER {self.label}: {self.elapsed:.2f}s")
