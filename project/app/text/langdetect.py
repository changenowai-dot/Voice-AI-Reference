"""Sprachplausibilitätsprüfung (Anforderung 8).

Die Nutzerauswahl wird NIE überschrieben. Wir prüfen nur, ob der Text
plausibel zur gewählten Sprache passt, und warnen bei klarem Widerspruch.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Hohe Signalstärke, kleine Listen reichen völlig
_DE_MARKERS = re.compile(
    r"\b(der|die|das|den|dem|ein|eine|und|oder|nicht|ist|sind|war|waren|hat|haben|"
    r"wird|werden|wurde|mit|von|zu|zum|zur|auf|für|im|in|am|an|aus|bei|nach|über|"
    r"man|auch|noch|nur|schon|sehr|aber|dass|weil|denn|wenn|als|wie|so|ja|nein|"
    r"kein|keine|mehr|immer|wieder| Between|zwischen|beim|durch|gegen|ohne|um)\b",
    re.IGNORECASE,
)
_EN_MARKERS = re.compile(
    r"\b(the|and|or|not|is|are|was|were|has|have|had|will|would|with|from|to|of|"
    r"in|on|at|by|for|about|into|over|after|between|that|this|these|those|it|its|"
    r"they|them|their|he|she|his|her|we|you|i|but|if|because|as|than|so|no|yes|"
    r"more|always|never|only|very|also|just|there|been|being|does|did|doing)\b",
    re.IGNORECASE,
)
_DE_ONLY_CHARS = set("äöüßÄÖÜ")


@dataclass
class LanguageCheck:
    selected: str
    detected_scores: dict
    plausible: bool
    warning: str = ""


def detect_language_scores(text: str) -> dict:
    """Heuristischer DE/EN-Score (0..1 Anteil an Markern pro Wort)."""
    words = re.findall(r"[A-Za-zÄÖÜäöüß]+", text)
    n = max(len(words), 1)
    de = len(_DE_MARKERS.findall(text))
    en = len(_EN_MARKERS.findall(text))
    uml = sum(1 for w in words if set(w.lower()) & _DE_ONLY_CHARS)
    de_score = de / n + min(uml / n, 0.15) * 2
    en_score = en / n
    return {"German": round(min(de_score, 1.0), 3),
            "English": round(min(en_score, 1.0), 3)}


def check_language_plausibility(text: str, selected: str) -> LanguageCheck:
    scores = detect_language_scores(text)
    sel = scores.get(selected, 0.0)
    other = scores.get("English" if selected == "German" else "German", 0.0)
    plausible = True
    warning = ""
    # klarer Widerspruch: andere Sprache mehr als doppelt so stark UND deutlich
    if other > 0.02 and sel > 0.0 and other > sel * 2.0:
        plausible = False
        other_name = "Englisch" if selected == "German" else "Deutsch"
        warning = (
            f"Der Text wirkt überwiegend {other_name} "
            f"(Score {other:.2f} vs. {sel:.2f} für die Auswahl). "
            "Bitte Sprache prüfen – die Auswahl wurde nicht geändert."
        )
    elif sel == 0.0 and other > 0.03:
        plausible = False
        other_name = "Englisch" if selected == "German" else "Deutsch"
        warning = f"Keine Marker der gewählten Sprache gefunden; Text wirkt {other_name}."
    return LanguageCheck(selected=selected, detected_scores=scores,
                         plausible=plausible, warning=warning)
