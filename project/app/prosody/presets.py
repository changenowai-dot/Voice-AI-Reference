"""Presets (Anforderung 26): Stilprofile für typische Inhalte.

Jedes Preset definiert: Basis-Stilbeschreibung (geht in den Qwen-Instruct
ein), Pausenstil, Standard-Emotion, Tempo-Empfehlung.
Voreingestellt ist „deep_documentary“ – der Hauptanwendungsfall.
"""
from __future__ import annotations

from .. import paths
from ..utils import read_json

PRESETS = {
    "deep_documentary": {
        "label": "Deep Documentary",
        "base_style": ("Speak as a deep, calm, highly credible documentary "
                       "narrator: warm, serious, intelligent, slightly "
                       "cinematic, never melodramatic."),
        "pause_style": "auto",
        "emotion": "AUTO",
        "intensity": "AUTO",
        "speed": 1.0,
        "description": "Psychologie, Philosophie, Geschichte, Deep Dives "
                       "(Standard)."
    },
    "psychological": {
        "label": "Psychological",
        "base_style": ("Speak as a thoughtful psychological narrator: calm, "
                       "empathetic, precise, drawing the listener in with "
                       "quiet intensity."),
        "pause_style": "relaxed",
        "emotion": "AUTO",
        "intensity": "AUTO",
        "speed": 0.97,
        "description": "Psychologische und emotionale Themen."
    },
    "cinematic": {
        "label": "Cinematic",
        "base_style": ("Speak like a cinematic trailer narrator with a deep, "
                       "measured, powerful voice: grave but controlled, "
                       "building quiet anticipation."),
        "pause_style": "relaxed",
        "emotion": "AUTO",
        "intensity": 3,
        "speed": 0.95,
        "description": "Dramaturgisch-kraftvolle Erzählung."
    },
    "investigative": {
        "label": "Investigative",
        "base_style": ("Speak as an investigative journalist: sharp, serious, "
                       "credible, with measured urgency and precise "
                       "articulation."),
        "pause_style": "tight",
        "emotion": "AUTO",
        "intensity": "AUTO",
        "speed": 1.0,
        "description": "Recherchen und Enthüllungen."
    },
    "calm_storytelling": {
        "label": "Calm Storytelling",
        "base_style": ("Speak as a gentle storyteller: warm, unhurried, "
                       "painting pictures with words, intimate and natural."),
        "pause_style": "relaxed",
        "emotion": "warm",
        "intensity": 2,
        "speed": 0.95,
        "description": "Ruhige, erzählerische Inhalte."
    },
    "documentary": {
        "label": "Documentary",
        "base_style": ("Speak as a professional documentary narrator: clear, "
                       "objective, credible, even pacing."),
        "pause_style": "auto",
        "emotion": "neutral",
        "intensity": 2,
        "speed": 1.0,
        "description": "Klassische Dokumentation."
    },
    "audiobook": {
        "label": "Audiobook / Narrator",
        "base_style": ("Speak like an experienced audiobook narrator: natural, "
                       "warm, attentive to the story, with smooth flow and "
                       "subtle characterization."),
        "pause_style": "auto",
        "emotion": "AUTO",
        "intensity": "AUTO",
        "speed": 1.0,
        "description": "Hörbuchartiges Erzählen langer Texte."
    },
    "custom": {
        "label": "Custom",
        "base_style": ("Speak as a professional narrator."),
        "pause_style": "auto",
        "emotion": "AUTO",
        "intensity": "AUTO",
        "speed": 1.0,
        "description": "Eigene Einstellungen (manuell anpassbar)."
    },
}


def load_presets() -> dict:
    """Presets aus config/presets.json, per Datei erweiterbar."""
    data = read_json(paths.PRESETS_FILE, None)
    if isinstance(data, dict) and data:
        merged = dict(PRESETS)
        merged.update(data)
        return merged
    return dict(PRESETS)


def get_preset(name: str) -> dict:
    presets = load_presets()
    return presets.get(name, presets["deep_documentary"])


def default_preset() -> str:
    return "deep_documentary"
