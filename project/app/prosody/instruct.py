"""Instruct-Builder (Phase 1 + Phase 2).

Phase 2 (§5–§12):
- Rollen aus dominanter Satzrolle des Segments (Mehr-Satz-sicher)
- Hinweis-Budget gegen Überbetonung (statement/calm/transition ohne
  Hinweis, Dramatik nie zwei Segmente in Folge)
- Formulierungs-Rotation des Konsistenz-Ankers gegen identische
  Satzend-Konturen (§9)
- Langsatz-Strukturierungshinweis (§11) und Short-Run-Build (§12)
- VoiceDesign-Beschreibungen (§3) für die Voice-Studio-Kandidaten

Bestandteile pro Segment-Instruct:
1. Varianten-Grundstil (Sprachidentität + Charakter)
2. Profil-Modifikator (z. B. Male 3 = extra tief/gewichtig)
3. AUTO-Emotion/Intensität aus dem Text
4. deutsche Satzrollen-Hinweise (Budget-gesteuert)
5. rotierender Konsistenz-Anker für Long-Form
"""
from __future__ import annotations

import re

from .german import (german_instruct_hints, dominant_role, hint_allowed,
                     profile_sentence, rotate_anchor)
from .variation import EMOTION_SET_DE, detect_subtle_emotion

EMOTIONS = ("AUTO", "neutral", "calm", "warm", "serious", "somber",
            "mysterious", "tense", "hopeful")

_EMOTION_INSTRUCT = {
    "neutral": "Keep a neutral, clear narration.",
    "calm": "Speak calmly and evenly, relaxed pacing.",
    "warm": "Speak with warmth and gentle friendliness.",
    "serious": "Speak seriously and with quiet authority.",
    "somber": "Speak in a somber, reflective tone.",
    "mysterious": "Speak with a subtle sense of mystery and quiet tension.",
    "tense": "Speak with quiet tension and urgency, never shouting.",
    "hopeful": "Speak with understated optimism and light.",
}

_INTENSITY_WORDS = {
    1: "very subtle",
    2: "subtle",
    3: "moderate",
    4: "pronounced",
    5: "strong",
}

# ---------------------------------------------------------------------------
# Systematisch testbare Instruct-Varianten für DEUTSCH (Phase 1)
# ---------------------------------------------------------------------------
INSTRUCT_VARIANTS: dict[str, dict] = {
    "de_doc_classic": {
        "label": "Classic (Baseline)",
        "text": ("Speak as a professional male documentary narrator in "
                 "German: calm, warm, highly credible, even pacing, "
                 "natural intonation."),
    },
    "de_doc_native": {
        "label": "Native German Documentary",
        "text": ("You are a native German documentary narrator. Speak with "
                 "native German pronunciation and natural German sentence "
                 "melody and rhythm – never English prosody. Deep, calm, "
                 "serious, warm and highly credible voice; measured, even "
                 "pacing; subtle cinematic gravity, never melodramatic."),
    },
    "de_audiobook": {
        "label": "German Audiobook",
        "text": ("You are a German audiobook narrator with a naturally warm, "
                 "intelligent voice. Native German pronunciation, flowing "
                 "German sentence music, unhurried pacing, immersive and "
                 "perfectly consistent."),
    },
    "de_psych": {
        "label": "Psychological Documentary",
        "text": ("You are an intelligent German psychological documentary "
                 "narrator: calm, empathetic, precise, quietly intense. "
                 "Native German pronunciation with natural German rhythm; "
                 "draw the listener in without drama."),
    },
    "de_restrained": {
        "label": "Restrained Documentary",
        "text": ("Restrained German documentary voice: serious, "
                 "authoritative, minimal emotional movement, very steady "
                 "pacing, native German intonation and articulation."),
    },
    "de_calm_authoritative": {
        "label": "Calm Authoritative",
        "text": ("Calm, authoritative German narrator: deep, grounded, "
                 "credible. Native German sentence melody, clear "
                 "articulation, relaxed but focused pacing."),
    },
    "de_cinematic": {
        "label": "Cinematic Deep",
        "text": ("You are the deep voice of a German cinematic documentary: "
                 "grave, calm, weighty, with quiet anticipation. Native "
                 "German pronunciation and rhythm; controlled power, "
                 "never shouting."),
    },
    "de_lang_de": {
        "label": "Deutsch formuliert",
        "text": ("Du bist ein deutscher Dokumentarsprecher: ruhig, tief, "
                 "glaubwürdig, warm, intelligent. Aussprache und "
                 "Satzmelodie muttersprachlich deutsch, natürliches "
                 "deutsches Sprechtempo, niemals übertrieben dramatisch."),
    },
}

DEFAULT_GERMAN_VARIANT = "de_doc_native"


# ---------------------------------------------------------------------------
# VoiceDesign-Beschreibungen (Phase 2, §3) – Ausgangspunkte A/B/C des
# Auftrags + verfeinerte eigene Varianten. KEIN „German accent“.
# ---------------------------------------------------------------------------
VOICEDESIGN_DESCRIPTIONS: dict[str, dict] = {
    "vd_a": {
        "label": "VoiceDesign A (Auftrag)",
        "description": ("Tiefer, ruhiger deutscher Dokumentarsprecher. "
                        "Professionell, seriös, warm und glaubwürdig. "
                        "Natürliche deutsche Aussprache. Zurückhaltende "
                        "emotionale Dynamik."),
    },
    "vd_b": {
        "label": "VoiceDesign B (Auftrag)",
        "description": ("Erwachsener deutscher männlicher Erzähler. Tiefe "
                        "warme Stimme. Ruhige und intelligente Präsentation. "
                        "Natürliche deutsche Satzmelodie. Dokumentarisch "
                        "und leicht cinematic."),
    },
    "vd_c": {
        "label": "VoiceDesign C (Auftrag)",
        "description": ("Professioneller deutscher Hörbuchsprecher. Tief, "
                        "ruhig und kontrolliert. Sehr natürliche deutsche "
                        "Aussprache. Feine emotionale Variationen. Keine "
                        "übertriebene Dramatisierung."),
    },
    "vd_d": {
        "label": "VoiceDesign D (verfeinert: glaubwürdiger Journalist)",
        "description": ("Ein erwachsener deutscher Sprecher mittleren Alters "
                        "mit natürlich tiefer, warmer Stimme. Er erzählt "
                        "ruhig und präzise wie ein seriöser Dokumentarfilm-"
                        "sprecher: deutsche Muttersprachler-Aussprache, "
                        "gleichmäßiges Tempo, dezente Betonung, große "
                        "Glaubwürdigkeit, ohne jede Dramatik."),
    },
    "vd_e": {
        "label": "VoiceDesign E (verfeinert: Hörbuch-Tiefe)",
        "description": ("Deutscher Erzähler mit reifer, ruhiger, etwas "
                        "rauchiger Stimme. Spricht langsam und bedacht, "
                        "warm und nah am Zuhörer, wie ein erfahrener "
                        "Hörbuchsprecher. Natürliche deutsche Betonung und "
                        "Satzmelodie, feine Emotionen, niemals theatralisch."),
    },
    "vd_f": {
        "label": "VoiceDesign F (verfeinert: philosophisch)",
        "description": ("Ruhige männliche deutsche Stimme von mittlerer "
                        "Tiefe, intelligent und besonnen. Vortrag wie in "
                        "einer gehaltvollen Doku über Philosophie: klare "
                        "Artikulation, weiche Übergänge, stille Spannung, "
                        "natürlicher Sprachfluss ohne Pathos."),
    },
}

# Referenztext für Design->Clone (kurz, repräsentativ für den Stil)
VOICEDESIGN_REF_TEXT_DE = (
    "Es gibt ein Buch, das niemand geschrieben haben will. Und doch hat es "
    "Generationen bewegt. Vielleicht, weil in ihm eine Frage steht, die "
    "niemand laut aussprechen möchte: Wer bestimmt, was wirklich ist?")


def variant_text(variant_id: str) -> str:
    v = INSTRUCT_VARIANTS.get(variant_id)
    if v:
        return v["text"]
    return variant_id if isinstance(variant_id, str) and variant_id else \
        INSTRUCT_VARIANTS[DEFAULT_GERMAN_VARIANT]["text"]


# AUTO-Erkennung: Schlüsselreize im Text – SPRACHGETRENNT.
# (Phase-3-Fix: gemischte Muster verursachten Fehlalarme im Deutschen,
#  z. B. engl. „war“ = somber gegen deutsches „… gestellt war?“.)
_PATTERNS_DE = [
    (re.compile(r"\b(geheim|mysteriös|ungelöst|Rätsel|Verschwörung|"
                r"verschwiegen|unbekannt|Unerklärliche|verboten)\b", re.I),
     "mysterious"),
    (re.compile(r"\b(Krieg|Tod|Verbrechen|Katastrophe|Tragödie|"
                r"Verzweiflung|Untergang|Zusammenbruch)\b", re.I), "somber"),
    (re.compile(r"\b(jedoch|Gefahr|Warnung|Bedrohung|Konflikt|Krise|"
                r"aber nun)\b", re.I), "tense"),
    (re.compile(r"\b(Hoffnung|Zukunft|Lösung|Erkenntnis|Fortschritt|"
                r"Wunder|Durchbruch)\b", re.I), "hopeful"),
    (re.compile(r"\b(zusammen|Herz|Menschlichkeit|Dank|Liebe)\b", re.I),
     "warm"),
]
_PATTERNS_EN = [
    (re.compile(r"\b(secret|mystery|unsolved|enigma|hidden|unknown)\b",
                re.I), "mysterious"),
    (re.compile(r"\b(war|death|crime|catastrophe|tragedy|despair|"
                r"collapse)\b", re.I), "somber"),
    (re.compile(r"\b(danger|warning|threat|crisis|conflict|alarming)\b",
                re.I), "tense"),
    (re.compile(r"\b(hope|future|solution|insight|progress|wonder|"
                r"breakthrough)\b", re.I), "hopeful"),
    (re.compile(r"\b(together|humanity|gratitude|heart)\b", re.I), "warm"),
]


def detect_emotion(text: str, language: str = "German") -> tuple[str, int]:
    """Heuristische AUTO-Erkennung: (Emotion, Intensität 1-5)."""
    patterns = _PATTERNS_DE if language.lower().startswith("ger") \
        else _PATTERNS_EN
    scores: dict[str, int] = {}
    for rx, emotion in patterns:
        n = len(rx.findall(text))
        if n:
            scores[emotion] = scores.get(emotion, 0) + n
    if not scores:
        return "neutral", 1
    emotion = max(scores, key=lambda k: scores[k])
    hits = scores[emotion]
    intensity = 1 if hits <= 1 else (2 if hits <= 3 else (3 if hits <= 6 else 4))
    if text.count("?") >= 2 and emotion == "neutral":
        emotion = "mysterious"
        intensity = max(intensity, 2)
    return emotion, intensity


def build_instruct(base_style: str, text: str, language: str, *,
                   emotion: str = "AUTO", intensity: str | int = "AUTO",
                   heading: bool = False,
                   profile_modifier: str = "",
                   german_variant: str | None = None,
                   seg_index: int = 0,
                   last_high_idx: int | None = None,
                   short_run_pos: str | None = None,
                   long_sentence: bool = False,
                   subtle_emotion: tuple | None = None,
                   emphasis_words: list | None = None,
                   collect_hints: bool = False) -> str | tuple[str, list[str]]:
    """Baut den Stil-Instruct für ein Segment.

    Phase-2-Steuerung über seg_index/last_high_idx/short_run_pos/
    long_sentence (Hinweis-Budget §7, Rotation §9, Short-Run §12).
    collect_hints: gibt zusätzlich die verwendeten Hinweise zurück.
    """
    is_german = language.lower().startswith("ger")
    parts: list[str] = []
    if is_german and german_variant:
        parts.append(variant_text(german_variant).strip().rstrip("."))
    else:
        parts.append(base_style.strip().rstrip("."))
    if profile_modifier:
        parts.append(profile_modifier.strip().rstrip("."))

    hints: list[str] = []

    if emotion == "AUTO":
        em, _ = detect_emotion(text, language)
    else:
        em = emotion if emotion in _EMOTION_INSTRUCT else "neutral"

    if intensity == "AUTO":
        _, inten = detect_emotion(text, language)
    else:
        try:
            inten = int(intensity)
        except (TypeError, ValueError):
            inten = 3
    inten = max(1, min(5, inten))

    # Emotion nur dosiert (§7): AUTO-Emotion neutral -> KEIN Emotionsteil
    em_text = _EMOTION_INSTRUCT.get(em, "")
    if em != "neutral" and em_text:
        parts.append(em_text)
        hints.append(em_text)
        intensity_line = f"Emotional coloring: {_INTENSITY_WORDS[inten]}."
        parts.append(intensity_line)
        hints.append(intensity_line)
    elif emotion == "neutral" and em_text:
        parts.append(em_text)
        hints.append(em_text)

    # Phase 3 (§21): subtile, inhaltsausgelöste Emotion VOR klassischer
    # Emotion (nur wenn keine explizite gewählt wurde) – niemals global
    if emotion == "AUTO" and em == "neutral" and is_german:
        sem, se_int = (subtle_emotion if subtle_emotion else
                       detect_subtle_emotion(text))
        if sem and se_int >= 2 and hint_allowed(seg_index, "emphasis",
                                                last_high_idx):
            line = EMOTION_SET_DE.get(sem, "")
            if line:
                parts.append(line)
                hints.append(line)

    # Rollen-Hinweise mit Budget (Phase 2 §7)
    if is_german:
        role = dominant_role(text)
        if hint_allowed(seg_index, role, last_high_idx):
            role_hints = german_instruct_hints(
                role, language, is_heading=heading,
                long_sentence=long_sentence,
                in_short_run=(short_run_pos is not None),
                run_position=short_run_pos)
            parts.extend(role_hints)
            hints.extend(role_hints)
    elif heading:
        parts.append("This line introduces a new section: announce it "
                     "calmly, then pause.")

    # Phase 3 (§19.7): semantische Betonung – sanft, budgetiert
    if emphasis_words and is_german and hint_allowed(
            seg_index, "emphasis", last_high_idx):
        quoted = ", ".join(f"'{w}'" for w in emphasis_words[:2])
        line = (f"Gently lean on {quoted} – a natural, small emphasis, "
                f"nothing forced.")
        parts.append(line)
        hints.append(line)

    # rotierender Konsistenz-Anker (§9)
    parts.append(rotate_anchor(seg_index))

    instruct = " ".join(parts)
    if collect_hints:
        return instruct, hints
    return instruct


def speed_instruct(speed: float, effective_speed: float | None = None) -> str:
    """Sanfte Tempo-Steuerung über Instruct."""
    eff = effective_speed if effective_speed is not None else speed
    if abs(eff - 1.0) < 0.03:
        return ""
    if eff < 1.0:
        return "Speak a bit slower than usual, measured and clear."
    return "Speak a bit faster than usual, still calm and clear."
