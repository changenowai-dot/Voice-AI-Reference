"""English prosody annotation and pause profiles.

Mirrors the structure of ``german.py`` (same API surface:
``profile_sentence``, ``dominant_role``, ``terminator_role``,
``english_instruct_hints``, ``PAUSE_BASE_EN``) so pauses.py can pick
language-appropriate roles and timings without branching the rest of
the pipeline.

Deterministic, rule-based, never mutates text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Sentence role cues (English)
# ---------------------------------------------------------------------------
_QUESTION_WORDS = re.compile(
    r"^\s*(Who|What|When|Where|Why|How|Which|Whom|Whose|Is|Are|Was|Were|"
    r"Do|Does|Did|Have|Has|Had|Can|Could|Would|Will|Should|Shall|May|"
    r"Might|Must|Ain't|Isn't|Aren't|Wasn't|Weren't|Don't|Doesn't|Didn't|"
    r"Hasn't|Haven't|Hadn't|Can't|Couldn't|Wouldn't|Won't|Shouldn't)\b",
    re.I)

_RHETORICAL_CUES = re.compile(
    r"\b(after all|really|truly|indeed|surely|perhaps|maybe|I wonder|"
    r"is it not|isn't it|aren't we|don't you|do you really|what if|why "
    r"would anyone|who could|how could)\b", re.I)

_RHET_SETUP = re.compile(
    r"^\s*(And|But|Yet|So|Then)\s+(who|what|when|where|why|how)\b", re.I)

_ENUMERATION = re.compile(
    r"\b(first(ly)?|second(ly)?|third(ly)?|next|then|finally|lastly|"
    r"furthermore|moreover|on one hand|on the other hand|either|neither|"
    r"both|not only|for one thing)\b", re.I)
_ENUM_MIN_COMMAS = 2

_CONTRAST = re.compile(
    r"\b(but|however|yet|although|though|even though|whereas|while|"
    r"in contrast|on the contrary|conversely|rather than|instead|"
    r"nevertheless|nonetheless|still)\b", re.I)

_EMPHASIS = re.compile(
    r"\b(precisely|exactly|indeed|truly|really|above all|especially|"
    r"crucially|importantly|notably|specifically|in fact|the key point|"
    r"what matters is)\b", re.I)

_EMOTIONAL = re.compile(
    r"\b(suddenly|forever|never|for the first time|for the last time|"
    r"never again|in that moment|pain|grief|hope|fear|love|terror|"
    r"devastating|shattering|overwhelming)\b", re.I)

_TRANSITION = re.compile(
    r"^\s*(Now|Today|Later|Years later|Soon|Then|And so|Yet|But|"
    r"Meanwhile|Back then|At that moment|Consider|Turn(ing)? to|"
    r"Let us|We turn|This brings us|What follows)\b", re.I)

_DRAMATIC_OPENERS = re.compile(
    r"^\s*(And then|But then|And yet|Yet|So|Then|Suddenly|Nothing|Everything|"
    r"There was|There is|It was)\b")

_EXPLANATION = re.compile(
    r"\b(because|since|meaning|that is|which means|in other words|"
    r"put simply|to clarify|essentially|namely|i\.e\.)\b", re.I)

_CALM = re.compile(
    r"\b(perhaps|maybe|somehow|somewhere|almost|nearly|quietly|"
    r"softly|gently|slowly)\b", re.I)

_SHORT_PUNCH_MAX_WORDS = 7

_ALL_ROLES = ("statement", "question", "rhetorical_question", "emphasis",
              "list", "contrast", "explanation", "dramatic", "transition",
              "calm", "emotional")


@dataclass
class EnglishSentenceProfile:
    role: str = "statement"
    is_main_clause: bool = True
    has_subordinate: bool = False
    word_count: int = 0
    ends_question: bool = False


def profile_sentence(text: str) -> EnglishSentenceProfile:
    t = text.strip()
    words = t.split()
    p = EnglishSentenceProfile(word_count=len(words),
                               ends_question=t.endswith("?"))
    if t.endswith("?"):
        if _RHETORICAL_CUES.search(t) or _RHET_SETUP.match(t):
            p.role = "rhetorical_question"
        elif _QUESTION_WORDS.match(t):
            p.role = "rhetorical_question" if len(words) <= 16 else "question"
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
        p.role = "dramatic"
    elif _TRANSITION.match(t):
        p.role = "transition"
    elif _EXPLANATION.search(t):
        p.role = "explanation"
    elif _DRAMATIC_OPENERS.match(t) and len(words) <= _SHORT_PUNCH_MAX_WORDS + 4:
        p.role = "dramatic"
    elif _CALM.search(t):
        p.role = "calm"
    elif _EMPHASIS.search(t):
        p.role = "emphasis"
    elif len(words) <= _SHORT_PUNCH_MAX_WORDS and t.endswith((".", "!")):
        p.role = "dramatic"
    return p


_ROLE_SALIENCE = {"rhetorical_question": 9, "question": 8, "dramatic": 7,
                  "emotional": 6, "contrast": 5, "transition": 4,
                  "explanation": 4, "list": 3, "emphasis": 3,
                  "calm": 1, "statement": 0}


def dominant_role(segment_text: str) -> str:
    from ..text.analyze import split_sentences
    sentences = split_sentences(segment_text) or [segment_text]
    scores: dict[str, float] = {}
    for i, s in enumerate(sentences):
        r = profile_sentence(s).role
        w = 2.0 if i == len(sentences) - 1 else 1.0
        scores[r] = scores.get(r, 0.0) + w * (_ROLE_SALIENCE.get(r, 0) + 1)
    return max(scores, key=lambda k: scores[k]) if scores else "statement"


# ---------------------------------------------------------------------------
# Short-run detection (English)
# ---------------------------------------------------------------------------
def detect_short_sentence_run(texts: list[str], max_words: int = 7) -> list[int]:
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
# Terminators (clause-level punctuation) — reused by narrative pauses
# ---------------------------------------------------------------------------
_TERMINATOR_TO_ROLE = {
    ".": "statement",
    "!": "exclamation",
    "?": "question",
    ";": "semicolon",
    ":": "colon",
    "-": "dash", "--": "dash", "—": "dash", "–": "dash",
    "...": "ellipsis", "…": "ellipsis",
    ",": "comma",
}


_TERMINATOR_CLOSERS = tuple("\"'”»)]")

def terminator_role(text: str) -> str | None:
    t = text.rstrip()
    while t and t[-1] in _TERMINATOR_CLOSERS:
        t = t[:-1]
    t = t.rstrip()
    if not t:
        return None
    # check 3-char ellipsis first, then single
    if t.endswith("..."):
        return "ellipsis"
    if t.endswith("…"):
        return "ellipsis"
    last = t[-1]
    return _TERMINATOR_TO_ROLE.get(last)


# ---------------------------------------------------------------------------
# English pause bases and strategies (per-language profiles).
#
# English naturally runs slightly tighter between sentences than German,
# but needs air at structural boundaries. Commas in English are lighter
# than in German; semicolons/colons/dashes carry more weight. Paragraph
# transitions are clearly marked, and headings/chapters land longer.
# ---------------------------------------------------------------------------
PAUSE_BASE_EN = {
    "statement": 0.38,
    "question": 0.52,
    "rhetorical_question": 0.68,
    "list": 0.46,
    "contrast": 0.52,
    "emphasis": 0.56,
    "explanation": 0.44,
    "transition": 0.58,
    "calm": 0.48,
    "dramatic": 0.82,
    "emotional": 0.62,
    "heading": 0.95,
    "heading_after": 0.62,
    "paragraph": 0.78,
    "chapter": 1.25,
    "list_item": 0.52,
    "quote_end": 0.70,
    "end_of_text": 0.95,
}

PAUSE_STRATEGIES_EN: dict[str, dict] = {
    "classic": {},
    "semantic": {
        "after_rhetorical": 1.18,
        "after_question": 1.00,
        "after_dramatic": 1.15,
        "transition_extra": 0.08,
        "list_factor": 0.85,
        "paragraph_min": 0.85,
    },
    "flow": {
        "statement": 0.32,
        "in_list": 0.38,
        "paragraph": 0.92,
        "chapter": 1.40,
        "after_rhetorical": 1.08,
    },
    # English narrative documentary: natural long-form breathing space;
    # clause pauses shorter than German but still audible; structural
    # pauses clearly marked without sounding mechanical.
    "narrative": {
        "statement": 0.54,
        "question": 0.78,
        "rhetorical_question": 1.00,
        "exclamation": 0.72,
        "explanation": 0.60,
        "contrast": 0.72,
        "emphasis": 0.78,
        "transition": 0.82,
        "calm": 0.64,
        "list": 0.58,
        "dramatic": 1.10,
        "emotional": 0.84,
        "paragraph": 1.20,
        "chapter": 1.90,
        "heading": 1.30,
        "heading_after": 0.90,
        "list_item": 0.68,
        "quote_end": 0.92,
        "end_of_text": 1.40,
        "after_comma": 0.28,       # lighter comma breath vs German
        "after_semicolon": 0.52,
        "after_colon": 0.54,
        "after_dash": 0.58,
        "after_ellipsis": 0.70,
        "in_list": 0.50,
        "after_rhetorical": 1.25,
        "after_question": 1.14,
        "after_dramatic": 1.30,
        "transition_extra": 0.14,
        "list_factor": 1.00,
        "paragraph_min": 1.10,
    },
}


# ---------------------------------------------------------------------------
# English instruct hints (for TTS)
# ---------------------------------------------------------------------------
def english_instruct_hints(profile_or_role, language: str = "English",
                           is_heading: bool = False,
                           long_sentence: bool = False,
                           in_short_run: bool = False,
                           run_position: str | None = None) -> list[str]:
    role = getattr(profile_or_role, "role", profile_or_role)
    if not language.lower().startswith("eng"):
        return []
    hints: list[str] = []
    if is_heading:
        hints.append("This line introduces a new section: deliver it with "
                     "calm, clear emphasis and settle into a pause after it.")
        return hints
    if in_short_run:
        if run_position == "first":
            hints.append("Begin a tight sequence of short phrases - quiet "
                         "and steady, like placing stones one by one.")
        elif run_position == "middle":
            hints.append("Continue the short-phrase sequence with subtle "
                         "added weight.")
        elif run_position == "last":
            hints.append("Land the final phrase of the short sequence "
                         "cleanly and leave a beat of silence.")
        return hints
    if role == "rhetorical_question":
        hints.append("This is a rhetorical question: let it hang gently "
                     "and leave space after it.")
    elif role == "question":
        hints.append("End with a natural English rising question intonation.")
    elif role == "list":
        hints.append("List the items with a steady English rhythm, slight "
                     "rises on each and a fall on the final item.")
    elif role == "contrast":
        hints.append("Mark the contrast subtly with a small beat before "
                     "the opposing phrase.")
    elif role == "emphasis":
        hints.append("Give the key phrase quiet weight - do not shout.")
    elif role == "explanation":
        hints.append("This sentence explains: settle into a clarifying "
                     "warm tone.")
    elif role == "dramatic":
        hints.append("Deliver this short line with quiet weight, slow "
                     "slightly, then breathe.")
    elif role == "emotional":
        hints.append("Let emotion show through restraint - controlled "
                     "warmth or gravity, never theatrical.")
    if long_sentence:
        hints.append("Shape this long sentence: light breaths at commas, "
                     "keep the thread, land clearly on the final word.")
    return hints
