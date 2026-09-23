"""GUI-Helfer (pur, ohne Tk – testbar)."""
from __future__ import annotations

import re

CHARS_PER_SECOND = {"German": 14.0, "English": 15.0}
SEGMENT_CHARS = 420

# ---------------------------------------------------------------------------
# GUI-Freilegung vorhandener Backend-Optionen (KEINE neue Logik):
# Alle Auswahl-Listen werden aus den autoritativen Code-Quellen gelesen
# (presets.load_presets / german.STYLE_FACTOR_DE / german.PAUSE_STRATEGIES /
# instruct._EMOTION_INSTRUCT) – keine hartcodierten Parallel-Listen.
# Standardwerte der GUI sind Platzhalter: NICHT gewaehlt = Key wird NICHT
# in den Job geschrieben = exakt bisheriges Backend-Verhalten.
# ---------------------------------------------------------------------------
PLACEHOLDER = "(Standard)"
PRESET_PLACEHOLDER = "(Backend-Standard)"   # nichts gewählt = Backend-Default


def preset_choices() -> list[tuple[str, str]]:
    """(key, anzeigetext) ALLER im Code vorhandenen Presets.

    Quelle: app.prosody.presets.load_presets() (inkl. config/presets.json-
    Erweiterung). Reihenfolge wie im Backend definiert.
    """
    from ..prosody.presets import load_presets
    out: list[tuple[str, str]] = []
    for key, p in load_presets().items():
        label = p.get("label") or key
        lang = p.get("language")
        tag = f", {lang}" if lang else ""
        out.append((key, f"{label} [{key}{tag}]"))
    return out


def pause_style_choices() -> list[str]:
    """Vorhandene pause_style-Werte (Quelle: STYLE_FACTOR_DE-Keys)."""
    from ..prosody.german import STYLE_FACTOR_DE
    ordered = ["auto", "tight", "relaxed"]
    rest = [k for k in STYLE_FACTOR_DE if k not in ordered]
    return ordered + rest


def pause_strategy_choices() -> list[str]:
    """Vorhandene pause_strategy-Werte (Quelle: PAUSE_STRATEGIES-Keys)."""
    from ..prosody.german import PAUSE_STRATEGIES
    ordered = ["classic", "semantic", "flow", "narrative"]
    rest = [k for k in PAUSE_STRATEGIES if k not in ordered]
    return ordered + rest


def emotion_choices() -> list[str]:
    """Vorhandene emotion-Werte (Quelle: instruct._EMOTION_INSTRUCT)."""
    from ..prosody.instruct import _EMOTION_INSTRUCT
    return ["AUTO"] + list(_EMOTION_INSTRUCT.keys())


def intensity_choices() -> list[str]:
    """Vorhandene intensity-Werte (Pipeline clamp: max(1, min(5, x)))."""
    return ["AUTO", "1", "2", "3", "4", "5"]


def apply_optional_settings(spec: dict, preset_key: str | None = None,
                            emotion: str | None = None,
                            intensity: str | None = None,
                            pause_style: str | None = None,
                            pause_strategy: str | None = None) -> dict:
    """Setzt NUR die ausdrücklich gewählten vorhandenen Parameter in den
    Job-Spec. Platzhalter/leer/None -> Key bleibt UNGESETZT -> bisheriges
    Backend-Verhalten (kein neues Default, kein Override).
    """
    def _clean(v: str | None) -> str | None:
        if v is None:
            return None
        v = str(v).strip()
        if not v or v.startswith("("):
            return None
        return v

    preset_key = _clean(preset_key)
    if preset_key:
        spec["preset"] = preset_key
    for key, val in (("emotion", emotion), ("intensity", intensity),
                     ("pause_style", pause_style),
                     ("pause_strategy", pause_strategy)):
        val = _clean(val)
        if val:
            spec[key] = val
    return spec


def text_stats(text: str, language: str = "German") -> dict:
    chars = len(text)
    words = len(re.findall(r"\S+", text))
    rate = CHARS_PER_SECOND.get(language, 14.0)
    est_seconds = chars / rate if chars else 0.0
    est_segments = max(1, -(-chars // SEGMENT_CHARS)) if chars else 0
    return {"chars": chars, "words": words,
            "est_seconds": round(est_seconds, 1),
            "est_minutes": round(est_seconds / 60.0, 1),
            "est_segments": int(est_segments)}


def format_duration(seconds: float) -> str:
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def format_eta(elapsed_s: float, percent: float) -> str:
    if percent is None or percent <= 1 or percent >= 99.5:
        return ""
    remaining = elapsed_s * (100.0 / max(percent, 0.5) - 1.0)
    if remaining < 5 or remaining > 6 * 3600:
        return ""
    return format_duration(remaining)


def voice_sort_key(voice: dict) -> int:
    """VD-E zuerst, dann Rest alphabetisch (GUI-Reihenfolge)."""
    if voice.get("voice_id") == "vd_e":
        return 0
    return 1


SPEECH_STAGES_DE = {
    "startup": "Backend wird gestartet",
    "text_ready": "Text vorbereitet",
    "split": "Text wird in Parts aufgeteilt",
    "part": "Nächster Part",
    "voice_load": "Stimme wird geladen",
    "model_load": "Modell wird geladen (einmalig)",
    "model_ready": "Modell bereit",
    "synthesis": "Sprachsynthese",
    "tts": "Sprachsynthese läuft",
    "qc": "Qualitätsprüfung (QC)",
    "assembling": "Segmente werden zusammengefügt",
    "concat": "FullScript wird zusammengefügt",
    "concat_done": "FullScript fertiggestellt",
    "speed": "Tempo wird angepasst",
    "mastering": "Mastering (YouTube-Lautheit)",
    "done": "Fertig",
    "benchmark_done": "Benchmark abgeschlossen",
    "error": "Fehler",
}


def stage_label(stage: str | None) -> str:
    if not stage:
        return ""
    return SPEECH_STAGES_DE.get(stage, stage)
