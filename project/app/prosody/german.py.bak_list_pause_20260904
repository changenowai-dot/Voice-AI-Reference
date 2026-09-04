"""Deutsche Prosodie-Annotation (Phase 1 + Phase 2 erweitert).

Phase 2 (§5–§12):
- Mehr Satzrollen: STATEMENT, QUESTION, RHETORICAL_QUESTION, EMPHASIS,
  LIST, CONTRAST, EXPLANATION, DRAMATIC, TRANSITION, CALM
- Segment-Mikrorollen: Short-Run-Build ("Sieben Prinzipien. Sieben
  Regeln. Eine einzige Ordnung."), Endungs-Rotation, Hinweis-Budget
  gegen Überbetonung (§7)
- Pausenstrategien (§10): classic (Phase 1), semantic, flow
- Instruct-Formulierungsrotation gegen identische Konturen (§9)

Deterministisch, rein regelbasiert, verändert niemals den Inhalt.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Satzrollen-Marker (Phase 1 + neue Phase-2-Rollen)
# ---------------------------------------------------------------------------
_QUESTION_WORDS = re.compile(
    r"^\s*(Wer|Was|Wann|Wo|Wohin|Woher|Warum|Weshalb|Wieso|Wie|Welche?[rs]?"
    r"|Wen|Wem|Wessen|Bist|Ist|Sind|War|Waren|Hat|Haben|Kann|Könnte|"
    r"Soll|Sollte|Will|Wollen|Darf|Muss|Gibt|Gab|Tut|Does|Do|Is|Are|"
    r"Can|Could|Would|Will|Did|What|Why|How|Who|Where|When)\b", re.I)

_RHETORICAL_CUES = re.compile(
    r"\b(denn|wohl|eigentlich|wirklich|etwa|nicht wahr|etwa nicht|"
    r"oder etwa nicht|etwa doch|etwa schon|je wohl)\b", re.I)

# rhetorisches Setup: "Doch was passiert, wenn …?" (§8)
_RHET_SETUP = re.compile(
    r"^\s*(Doch|Aber)\s+(was|wer|wenn|warum|wohin|wie)\b", re.I)

_ENUMERATION = re.compile(
    r"\b(erst|zuerst|danach|dann|anschließend|schließlich|zuletzt|"
    r"einerseits|andererseits|sowohl|als auch|weder|noch|"
    r"first|then|finally)\b", re.I)
_ENUM_MIN_COMMAS = 2

_CONTRAST = re.compile(
    r"\b(aber|jedoch|doch|hingegen|allerdings|dennoch|trotzdem|"
    r"nicht nur|sondern|im Gegensatz|während hingegen|"
    r"but|however|yet|although)\b", re.I)

_EMPHASIS = re.compile(
    r"\b(genau|ausgerechnet|tatsächlich|wirklich|ausdrücklich|"
    r"vor allem|besonders|allein|einzig|exakt|"
    r"precisely|exactly)\b", re.I)

_EMOTIONAL = re.compile(
    r"\b(plötzlich|doch dann|in dieser Nacht|für immer|niemals|"
    r"zum ersten Mal|zum letzten Mal|nie wieder|"
    r"Angst|Liebe|Tod|Verzweiflung|Hoffnung|Trauer|Wut|Schmerz)\b", re.I)

_DRAMATIC_OPENERS = re.compile(
    r"^\s*(Doch|Und dann|Aber dann|Plötzlich|Denn|Weil|Tatsächlich|"
    r"Heute|Damals|Und)\b")

_SHORT_PUNCH_MAX_WORDS = 6

# --- NEU (Phase 2, §6) ------------------------------------------------------
_EXPLANATION = re.compile(
    r"\b(denn|nämlich|das heißt|das heißt:|gemeint ist|mit anderen Worten|"
    r"genauer gesagt|genauer:|denn schließlich|schließlich nämlich|"
    r"also|d. h.)\b|[,:]\s*(denn|nämlich)\b", re.I)

_TRANSITION = re.compile(
    r"^\s*(Doch|Dann|Später|Jahre später|Nun|Heute|Damals|Damit|"
    r"Anschließend|Bald|Viele Jahre|Im Jahr|Zur gleichen Zeit|"
    r"Kehren wir|Wenden wir uns|Betrachten wir|Come|Then|Now|Today)\b")

_CALM = re.compile(
    r"\b(vielleicht|wohl|irgendwie|irgendwo|eigentlich|fast|beinahe|"
    r"leise|ruhig|sanft|möglicherweise|gewissermaßen)\b", re.I)

_SUBORDINATE = re.compile(
    r"\b(weil|obwohl|damit|während|sobald|bevor|nachdem|seitdem|"
    r"wenn|falls|sodass|indem|der|die|das|welche?[rs]?)\b\s+"
    r"[a-zäöüß]+\b", re.I)

_ALL_ROLES = ("statement", "question", "rhetorical_question", "emphasis",
              "list", "contrast", "explanation", "dramatic", "transition",
              "calm")


@dataclass
class GermanSentenceProfile:
    role: str = "statement"
    is_main_clause: bool = True
    has_subordinate: bool = False
    word_count: int = 0
    ends_question: bool = False


def profile_sentence(text: str) -> GermanSentenceProfile:
    t = text.strip()
    words = t.split()
    p = GermanSentenceProfile(word_count=len(words),
                              ends_question=t.endswith("?"))
    p.has_subordinate = bool(_SUBORDINATE.search(t))
    if t.endswith("?"):
        if _RHETORICAL_CUES.search(t) or _RHET_SETUP.match(t):
            p.role = "rhetorical_question"
        elif _QUESTION_WORDS.match(t):
            p.role = "rhetorical_question" if len(words) <= 14 else "question"
        else:
            p.role = "question"
    elif _ENUMERATION.search(t) and (t.count(",") >= _ENUM_MIN_COMMAS or
                                     len(_ENUMERATION.findall(t)) >= 2):
        p.role = "list"
    elif _CONTRAST.search(t):
        p.role = "contrast"
    elif _EMOTIONAL.search(t):
        p.role = "emotional"
    elif _TRANSITION.match(t) and len(words) <= _SHORT_PUNCH_MAX_WORDS:
        p.role = "dramatic"          # kurzer Beat ("Dann kam die Stille.")
    elif _TRANSITION.match(t) and not _DRAMATIC_OPENERS.match(t):
        p.role = "transition"
    elif _EXPLANATION.search(t):
        p.role = "explanation"
    elif _DRAMATIC_OPENERS.match(t) and len(words) <= _SHORT_PUNCH_MAX_WORDS + 6:
        p.role = "dramatic"
    elif _CALM.search(t):
        p.role = "calm"
    elif _EMPHASIS.search(t):
        p.role = "emphasis"
    elif len(words) <= _SHORT_PUNCH_MAX_WORDS and t.endswith((".", "!")):
        p.role = "dramatic"
    return p


# Salienz-Reihenfolge für Segment-Mehr-Satz-Fälle (letzte zählt doppelt)
_ROLE_SALIENCE = {"rhetorical_question": 9, "question": 8, "dramatic": 7,
                  "emotional": 6, "contrast": 5, "transition": 4,
                  "explanation": 4, "list": 3, "emphasis": 3,
                  "calm": 1, "statement": 0}


def dominant_role(segment_text: str) -> str:
    """Bestimmt die prägende Rolle eines (Mehr-Satz-)Segments."""
    from ..text.analyze import split_sentences
    sentences = split_sentences(segment_text) or [segment_text]
    scores: dict[str, float] = {}
    for i, s in enumerate(sentences):
        r = profile_sentence(s).role
        w = 2.0 if i == len(sentences) - 1 else 1.0   # Satzende wiegt mehr
        scores[r] = scores.get(r, 0.0) + w * (_ROLE_SALIENCE.get(r, 0) + 1)
    return max(scores, key=lambda k: scores[k]) if scores else "statement"


# ---------------------------------------------------------------------------
# Short-Run-Build (§12): "Sieben Prinzipien. Sieben Regeln. Eine Ordnung."
# ---------------------------------------------------------------------------
def detect_short_sentence_run(texts: list[str],
                              max_words: int = 7) -> list[int]:
    """Indizes zusammenhängender kurzer Sätze/Segmente (>=2)."""
    runs: list[list[int]] = []
    current: list[int] = []
    for i, t in enumerate(texts):
        short = 0 < len(t.split()) <= max_words and not t.rstrip().endswith("?")
        if short:
            current.append(i)
        else:
            if len(current) >= 2:
                runs.append(current)
            current = []
    if len(current) >= 2:
        runs.append(current)
    return [i for run in runs for i in run]


# ---------------------------------------------------------------------------
# Hinweis-Budget (§7): Überbetonung vermeiden
# ---------------------------------------------------------------------------
_HIGH_AROUSAL = {"dramatic", "emotional", "emphasis"}


def hint_allowed(idx: int, role: str, last_high: int | None) -> bool:
    """Ob ein Rollen-Hinweis gesetzt wird.

    Regeln: statement/calm/transition/explanation erhalten standardmäßig
    KEINEN Hinweis (natürliche Lesart). Hochdramatische Rollen nie zwei
    Segmente in Folge (Abstand >= 2).
    """
    if role in ("statement", "calm", "transition"):
        return False
    if role in _HIGH_AROUSAL:
        if last_high is not None and idx - last_high < 2:
            return False
        return True
    return True            # question/list/contrast/explanation(END)


def rotate_anchor(idx: int) -> str:
    """Rotation der Konsistenz-Formulierung (§9): verhindert, dass eine
    identische Instruct-Zeile jede Segment-Kontur gleich lockt."""
    variants = (
        "Keep voice identity, pace and loudness perfectly consistent.",
        "Stay perfectly consistent: same voice, tempo and volume as before.",
        "Remain consistent with the same narrator voice, pace and loudness.",
    )
    return variants[idx % len(variants)]


# ---------------------------------------------------------------------------
# Pausenstrategien (§10)
# ---------------------------------------------------------------------------
PAUSE_BASE_DE = {
    "statement": 0.42,
    "question": 0.58,
    "rhetorical_question": 0.74,
    "list": 0.50,
    "contrast": 0.56,
    "emphasis": 0.62,
    "explanation": 0.46,
    "transition": 0.62,
    "calm": 0.50,
    "dramatic": 0.88,
    "emotional": 0.66,
    "heading": 1.05,
    "heading_after": 0.70,
    "paragraph": 0.86,
    "chapter": 1.35,
    "list_item": 0.58,
    "quote_end": 0.76,
    "end_of_text": 1.05,
}

PAUSE_STRATEGIES: dict[str, dict] = {
    # Phase-1-Verhalten (Referenz)
    "classic": {},
    # semantisch gewichtet: mehr Raum nach Fragen/Dramatik,Atmung bei
    # Transitionen, fester Fluss in Aufzählungen
    "semantic": {
        "after_rhetorical": 1.30,
        "after_question": 1.10,
        "after_dramatic": 1.25,
        "transition_extra": 0.10,
        "list_factor": 0.85,
        "paragraph_min": 0.95,
    },
    # Erzählfluss: innerhalb Absätze knapper, Grenzen deutlicher
    "flow": {
        "statement": 0.36,
        "in_list": 0.42,
        "paragraph": 1.00,
        "chapter": 1.50,
        "after_rhetorical": 1.20,
    },
}


# ---------------------------------------------------------------------------
# Instruct-Hinweise (deutsche Satzmelodie, §13 + Phase 2 verfeinert)
# ---------------------------------------------------------------------------
def german_instruct_hints(profile_or_role, language: str = "German",
                          is_heading: bool = False,
                          long_sentence: bool = False,
                          in_short_run: bool = False,
                          run_position: str | None = None) -> list[str]:
    """Zielgerichtete, kurze Hinweise – Budget regelt die Häufigkeit (§7)."""
    role = getattr(profile_or_role, "role", profile_or_role)
    if not language.lower().startswith("ger"):
        hints = []
        if role in ("question", "rhetorical_question"):
            hints.append("End with a natural rising question intonation.")
        return hints
    hints: list[str] = []
    if is_heading:
        hints.append("This line introduces a new section: announce it "
                     "calmly with a slight formal emphasis, then pause.")
        return hints
    # Short-Run-Build (§12): erzählerische Dynamik statt Gleichförmigkeit
    if in_short_run:
        if run_position == "first":
            hints.append("This begins a rhythmic sequence of short phrases: "
                         "start flat and quiet, like setting stones in a row.")
        elif run_position == "middle":
            hints.append("Continue the short-phrase sequence with slightly "
                         "more weight than before – quiet momentum.")
        elif run_position == "last":
            hints.append("This closes the short-phrase sequence: let it "
                         "fall and settle, then leave space.")
        return hints
    if role == "rhetorical_question":
        hints.append("This is a rhetorical question in German: let it rise "
                     "gently and leave space after it – do not answer it.")
    elif role == "question":
        hints.append("End with a natural German rising question melody.")
    elif role == "list":
        hints.append("Enumerate the items evenly with slight rises and let "
                     "the final item fall – natural German listing rhythm.")
    elif role == "contrast":
        hints.append("Mark the contrast subtly with a small pause before "
                     "the opposing phrase and slight emphasis on it.")
    elif role == "emphasis":
        hints.append("Give the key phrase a calm, deliberate emphasis "
                     "without raising your voice.")
    elif role == "explanation":
        hints.append("This sentence explains: slow down slightly and speak "
                     "it with clarifying warmth.")
    elif role == "dramatic":
        hints.append("Deliver this short sentence with quiet weight, "
                     "slower, then let it breathe.")
    elif role == "emotional":
        hints.append("Let the emotion show in a controlled, restrained way "
                     "– warmth in the voice, never theatrical.")
    if long_sentence:
        hints.append("Structure this long sentence: breathe lightly at the "
                     "commas, keep the main thread, land clearly at the end.")
    return hints


def summarize_roles(segments_texts: list[str]) -> dict:
    """Rollenhäufigkeit für Berichte/QC."""
    roles: dict[str, int] = {}
    for t in segments_texts:
        r = dominant_role(t)
        roles[r] = roles.get(r, 0) + 1
    return roles
