"""Natürliche Variation & subtile Emotion (Phase 3, §21–§22, §7).

Grundsatz: Variation ist SEMANTISCH MOTIVIERT (§22) und subtil (§21 —
Emotion ≠ Dramatisierung). Die Maßnahmen verändern die STIMME nicht
(§23: Referenz-erhaltend): sie wirken auf Sampling-Streuung, Pausen-
dramaturgie und – nur im CustomVoice-Modus – auf Formulierungs-Hinweise.

Bestandteile:
- EMOTION_SET_DE     : subtile emotionale Zustände (Nutzer-Liste §21)
- detect_subtle_emotion(): Inhalts-Auslöser (nicht global emotionalisieren)
- ROLE_SAMPLING      :.rollenabh. Sampling-Offsets (±0.08 max)
- emphasis_targets() : 1–2 semantische Schlüsselwörter je Satz
- variation_report() : Langform-Variationsmetriken (Monotonie-Detektor)
"""
from __future__ import annotations

import re

import numpy as np

# ---------------------------------------------------------------------------
# Subtile Emotionen (§21) – nur wenn der Inhalt sie auslöst
# ---------------------------------------------------------------------------
EMOTION_SET_DE = {
    "curious":      "Speak with quiet curiosity, as if genuinely wondering.",
    "reflective":   "Speak softly and reflectively, as if thinking along.",
    "serious":      "Speak seriously and with quiet weight.",
    "surprised":    "Let a brief, controlled note of surprise show.",
    "suspense":     "Build quiet suspense; hold something back.",
    "menace":       "Speak with a subtle dark undertone, never loud.",
    "awe":          "Speak with grounded, quiet awe.",
    "calm":         "Speak calmly and evenly.",
    "confident":    "Speak with calm certainty.",
    "doubtful":     "Sound gently doubtful, weighing the words.",
    "realization":  "Let a moment of realization shine through, then "
                    "continue calmly.",
    "skeptical":    "Sound politely skeptical, like raising one eyebrow.",
    "warm":         "Speak with warmth and gentle friendliness.",
    "hopeful":      "Speak with understated optimism.",
    "somber":       "Speak in a somber, reflective tone.",
}

# Inhalts-Auslöser (DE) – Reihenfolge = Priorität
_EMOTION_TRIGGERS: list[tuple[re.Pattern, str, int]] = [
    (re.compile(r"\b(sogenannte[rs]?|angeblich|vorgeblich|behauptet|"
                r"angebliche[rsm]?)\b", re.I), "skeptical", 2),
    (re.compile(r"\b(vielleicht irren|wer weiß|fraglich|zweifelhaft|"
                r"vielleicht nicht|unwahrscheinlich)\b", re.I), "doubtful", 2),
    (re.compile(r"\b(dann wird klar|plötzlich klar|verstehen wir|"
                r"Erkenntnis|es geht eigentlich um|im Kern)\b", re.I),
     "realization", 2),
    (re.compile(r"\b(Unendlich|unfassbar|gewaltig|Staunen|Wunder|"
                r"Tausende|Milliarden)\b", re.I), "awe", 2),
    (re.compile(r"\b(droht|Bedrohung|dunkle[rs]?|unheilvoll|Gefahr schwebt|"
                r"lauert|wartete etwas)\b", re.I), "menace", 2),
    (re.compile(r"\b(plötzlich|überraschend|unerwartet|und doch dann|"
                r"doch dann)\b", re.I), "surprised", 2),
    (re.compile(r"\b(hinter der|Spannung|lauert|beobachtet|wartet|"
                r"noch nicht zu Ende|nie gesagt)\b", re.I), "suspense", 1),
    (re.compile(r"\b(gewiss|zweifelsfrei|sicher|notwendig|unvermeidlich|"
                r"wird gelingen|Werden wir)\b", re.I), "confident", 1),
    (re.compile(r"\b(Was aber,? wenn|Was wäre|Wie wäre|herausfinden|"
                r"entdecken|wissen wollen|Frage lautet|Warum aber|"
                r"Was geschieht wirklich|Wer entscheidet)\b", re.I),
     "curious", 2),
    (re.compile(r"\b(nachdenken|vielleicht liegt|leise|still|"
                r"nachdenklich|versinken|Erinnerung)\b", re.I),
     "reflective", 2),
]


def detect_subtle_emotion(text: str) -> tuple[str | None, int]:
    """(Emotion|None, Intensität 1–3) – nur bei klarem Inhalts-Auslöser."""
    hits: list[tuple[str, int]] = []
    for rx, emotion, weight in _EMOTION_TRIGGERS:
        if rx.search(text):
            hits.append((emotion, weight))
    if not hits:
        return None, 0
    hits.sort(key=lambda hw: -hw[1])
    return hits[0][0], min(3, hits[0][1])


# ---------------------------------------------------------------------------
# Rollenabh. Sampling-Offsets (§22, subtil; wirkt in beiden Engine-Modi)
# ---------------------------------------------------------------------------
ROLE_SAMPLING: dict[str, dict] = {
    "dramatic":            {"temperature": +0.08},
    "emotional":           {"temperature": +0.07},
    "rhetorical_question": {"temperature": +0.05},
    "question":            {"temperature": +0.03},
    "contrast":            {"temperature": +0.04},
    "emphasis":            {"temperature": +0.04},
    "list":                {"temperature": -0.02},
    "statement":           {"temperature": 0.00},
    "explanation":         {"temperature": +0.01},
    "transition":          {"temperature": 0.00},
    "calm":                {"temperature": -0.02},
}

_TEMP_MIN, _TEMP_MAX = 0.55, 0.92


def sampling_offsets(role: str, emotion: str | None = None,
                     intensity: int = 0,
                     strength: str = "subtle") -> dict:
    """Sampling-Delta für ein Segment (Referenz-erhaltend klein)."""
    factor = 1.0 if strength == "subtle" else (1.6 if strength ==
                                               "expressive" else 0.0)
    if factor == 0.0:
        return {}
    delta = ROLE_SAMPLING.get(role, {}).get("temperature", 0.0)
    if emotion and intensity >= 2:
        delta += 0.02 * intensity
    if delta == 0.0:
        return {}
    return {"temperature": round(delta * factor, 3)}


def apply_sampling_offsets(base_sampling: dict, offsets: dict) -> dict:
    out = dict(base_sampling)
    if "temperature" in offsets:
        t = float(out.get("temperature", 0.7)) + offsets["temperature"]
        out["temperature"] = round(min(max(t, _TEMP_MIN), _TEMP_MAX), 3)
    return out


# ---------------------------------------------------------------------------
# Semantische Betonung (§19.7): 1–2 Schlüsselwörter je Satz
# ---------------------------------------------------------------------------
_SALIENCE_NOUNS = re.compile(
    r"\b(Schlüssel|Bauplan|Geheimnis|Wirklichkeit|Wahrheit|Wissen|Gesetz|"
    r"Prinzip|Regel|Ordnung|Antwort|Frage|Macht|Gefahr|Zeit|Tod|Leben|"
    r"Seele|Bewusstsein|Universum|Welt|Buch|Weg|Beweis|Versprechen|"
    r"Siegel|Kraft|Rätsel|Licht|Finsternis|Schlüssel|Zugang)\b")
_SUPERLATIVES = re.compile(
    r"\b(wichtigste[rsnm]?|einzige[rsnm]?|erste[rsnm]?|letzte[rsnm]?|"
    r"größte[rsnm]?|tiefste[rsnm]?|höchste[rsnm]?|wahre[rsnm]?|"
    r"eigentliche[rsnm]?|genaue[rsnm]?|ganze[rsnm]?)\b")
_NEGATIONS = re.compile(r"\b(niemals|nie|nicht|kein\w*|niemand|nichts)\b")
_STOP = set("der die das den dem ein eine einen und oder aber doch denn "
            "ist sind war waren wird werden hat haben kann muss soll "
            "wie was wer wenn weil dass für mit von zu im in an auf aus "
            "sich es er sie wir ihr man auch noch nur schon sehr hier "
            "dann dort so als ob ja nein mehr immer wieder".split())


def emphasis_targets(text: str, max_words: int = 2) -> list[str]:
    """1–2 semantisch wichtigste Wörter (für Betonungs-Hinweis/QC).

    Deutsche Satzgewichtung: das Rhema liegt tendenziell am Ende –
    daher werden die LETZTEN Salienz-Nomina gewählt. Direkt negierte
    Begriffe („nicht zu einem Geheimnis, sondern …“) werden übersprungen.
    """
    hits: list[str] = []
    for rx in (_SUPERLATIVES, _SALIENCE_NOUNS):
        for m in rx.finditer(text):
            w = m.group(0)
            if w.lower() in _STOP:
                continue
            before = text[max(0, m.start() - 24):m.start()].lower()
            if re.search(r"\b(nicht|kein\w*|weder)\b[^.!?]{0,40}$",
                         before):
                continue                      # negierter Begriff
            if w not in hits:
                hits.append(w)
    if not hits:
        return [m.group(0) for m in _NEGATIONS.finditer(text)][:max_words]
    return hits[-max_words:]                  # Satzende-Gewicht


# ---------------------------------------------------------------------------
# Langform-Variationsmetriken (§19.8 / §22)
# ---------------------------------------------------------------------------
def variation_report(wavs: list, srs: list, pause_values: list) -> dict:
    """Misst Variation über Segmente: Tonhöhe, Pausen, Tempo.

    Monotonie-Indikatoren: F0-Spread über Segmente zu klein
    (identische Tonhöhe), Pausen-CV zu klein (identische Pausen),
    Dauer-Raten-CV zu klein (mechanisches Tempo).
    """
    from ..quality.german_score import f0_series
    meds = []
    rates = []
    for wav, sr, txt_hint in zip(wavs, srs, [None] * len(wavs)):
        series = [f for _, f in f0_series(np.asarray(wav, dtype=np.float32),
                                          sr) if f > 0]
        if series:
            meds.append(float(np.median(series)))
        rates.append(len(wav) / sr)
    out: dict = {"n": len(wavs)}
    if len(meds) >= 3:
        f0_cv = float(np.std(meds) / max(np.mean(meds), 1e-6))
        out["f0_spread_cv"] = round(f0_cv, 4)
        out["f0_monotone"] = f0_cv < 0.015       # §22 identische Tonhöhe
    if len(pause_values) >= 4:
        p_cv = float(np.std(pause_values) / max(np.mean(pause_values), 1e-6))
        out["pause_cv"] = round(p_cv, 4)
        out["pauses_identical"] = p_cv < 0.05
    if len(rates) >= 3:
        d_cv = float(np.std(rates) / max(np.mean(rates), 1e-6))
        out["duration_cv"] = round(d_cv, 4)
        out["tempo_mechanical"] = d_cv < 0.04
    out["varied"] = not any(out.get(k) for k in
                            ("f0_monotone", "pauses_identical",
                             "tempo_mechanical"))
    return out
