"""Textanalyse (Anforderung 10): Struktur und Problemstellen erkennen,
ohne den Inhalt zu verändern.

Erkennt: Kapitel, Absätze, Sätze, Überschriften, Zitate, Listen, Zahlen,
Jahreszahlen, Datumsangaben, Uhrzeiten, Namen, Orte, Unternehmen, Fremdwörter,
Akronyme, Abkürzungen, technische Begriffe, rhetorische Passagen.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .numbers import roman_to_int

_HEADING_MD = re.compile(r"^#{1,6}\s+")
_HEADING_KNOWN = re.compile(
    r"^(kapitel|chapter|teil|part|abschnitt|prolog|epilog|einleitung|"
    r"intro(?:duktion)?|schlussteil|schluß|schluss|vorwort|anhang|quellen|"
    r"zusammenfassung|fa[zß]it)\b", re.IGNORECASE)

TECHNICAL_TERMS_DE = [
    "Neurotransmitter", "Kognition", "Dissonanz", "Prägung", "Trauma",
    "Verdrängung", "Libido", "Enthemmung", "Konditionierung", "Bias",
    "Dopamin", "Serotonin", "Cortisol", "Amygdala", "Präfrontalen",
    "Neuron", "Synapse", "Quanten", "Relativitätstheorie", "Entropie",
    "Algorithmus", "Neuronales Netz", "Bewusstsein", "Subliminal",
]
FOREIGN_HINTS = re.compile(
    r"\b(?:[A-Za-z]+-(?:Effect|Law|Syndrome|Principle)|"
    r"(?:the|of|and|mind|brain|self|science|theory|study)\b)", re.IGNORECASE)


@dataclass
class Block:
    """Struktureller Abschnitt des Textes."""
    kind: str              # heading | paragraph | list_item | quote | chapter_break
    text: str
    level: int = 0


@dataclass
class TextStats:
    chars: int = 0
    words: int = 0
    sentences: int = 0
    paragraphs: int = 0
    chapters: int = 0
    headings: int = 0
    list_items: int = 0
    quotes: int = 0
    numbers: int = 0
    years: int = 0
    dates: int = 0
    times: int = 0
    percentages: int = 0
    currencies: int = 0
    abbreviations: int = 0
    acronyms: int = 0
    names_capitalized: int = 0
    proper_noun_candidates: list = field(default_factory=list)
    technical_terms: list = field(default_factory=list)
    foreign_word_candidates: list = field(default_factory=list)
    questions: int = 0
    exclamations: int = 0
    quotes_marked: int = 0
    estimated_seconds: float = 0.0


@dataclass
class AnalysisResult:
    stats: TextStats
    blocks: list          # Liste[Block]
    language_scores: dict


def split_blocks(text: str) -> list[Block]:
    """Zerlegt Text in Absätze/Überschriften/Listen/ Zitate (Struktur)."""
    blocks: list[Block] = []
    for raw_para in re.split(r"\n\s*\n", text.strip()):
        para = raw_para.strip("\n").strip()
        if not para:
            continue
        lines = [l.rstrip() for l in para.split("\n") if l.strip()]
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # Zuerst eindeutige Strukturen (Listen, Zitate), dann Überschriften
            if re.match(r"^[-*•·]\s+", stripped):
                blocks.append(Block("list_item",
                                    re.sub(r"^[-*•·]\s+", "", stripped)))
                continue
            if re.match(r"^\d+[.)]\s+", stripped) and len(stripped) < 240:
                blocks.append(Block("list_item",
                                    re.sub(r"^\d+[.)]\s+", "", stripped)))
                continue
            if stripped.startswith(">"):
                blocks.append(Block("quote", stripped.lstrip("> ").strip()))
                continue
            if (stripped.startswith("„") and stripped.endswith("“")) or \
               (stripped.startswith('"') and stripped.endswith('"')) or \
               (stripped.startswith("»") and stripped.endswith("«")):
                blocks.append(Block("quote", stripped))
                continue
            md = _HEADING_MD.match(stripped)
            if md:
                blocks.append(Block("heading", stripped[md.end():].strip(),
                                    level=len(md.group(0).strip())))
                continue
            if _HEADING_KNOWN.match(stripped) and len(stripped) < 80:
                blocks.append(Block("heading", stripped, level=2))
                continue
            # Überschrift ohne Satzzeichen: kurze Zeile ohne Verb-Endung
            if (len(stripped) < 70 and not stripped.endswith((".", "!", "?", ",",
                    ":", ";"))
                    and stripped.count(" ") <= 8 and not stripped[0].islower()):
                blocks.append(Block("heading", stripped, level=3))
                continue
            blocks.append(Block("paragraph", stripped))
    return blocks


_SENT_SPLIT_ABBR = [
    "z.B", "z. B", "u.a", "u. a", "d.h", "d. h", "v.Chr", "v. Chr", "n.Chr",
    "n. Chr", "etc", "ca", "bzw", "ggf", "usw", "bspw", "Nr", "Dr", "Prof",
    "St", "Abs", "Art", "Jh", "Mr", "Mrs", "Ms", "St", "No", "Vol", "Fig",
    "ca", "evtl", "ggfs",
]
_ABBR_BOUNDARY = re.compile(
    r"(?<!\b" + r")(?<!\b".join(re.escape(a) for a in _SENT_SPLIT_ABBR) + r")")


def split_sentences(paragraph: str) -> list[str]:
    """Satzgrenzen für Deutsch/Englisch, robust gegenüber Abkürzungen,
    Dezimalzahlen und Initialen."""
    prot = paragraph
    # Abkürzungspunkte schützen
    for a in _SENT_SPLIT_ABBR:
        prot = prot.replace(a + ".", a + "\x00")
    # Dezimaltrenner schützen: 3,5 -> 3\x015 ; 3.5 -> 3\x025
    prot = re.sub(r"(\d),(\d)", "\\1\x01\\2", prot)
    prot = re.sub(r"(\d)\.(\d)", "\\1\x02\\2", prot)
    # Ordinalpunkte ("am 1. Mai") schützen
    prot = re.sub(r"\b(\d{1,2})\.(?=\s(?:Januar|Februar|März|April|Mai|Juni|"
                  r"Juli|August|September|Oktober|November|Dezember|January|"
                  r"February|March|May|June|July|October|December)\b)", "\\1\x00", prot)
    # Initialen "J. R. R." schützen
    prot = re.sub(r"\b([A-ZÄÖÜ])\.\s*(?=[A-ZÄÖÜ]\.)", "\\1\x00 ", prot)
    prot = re.sub(r"\b([A-ZÄÖÜ])\.(?=\s+[A-ZÄÖÜ][a-zäöü])", "\\1\x00 ", prot)

    parts = re.split(r"(?<=[.!?…])\s+(?=[\"„»A-ZÄÖÜ0-9])", prot)
    sentences = []
    for p in parts:
        s = (p.replace("\x00", ".")
              .replace("\x01", ",")
              .replace("\x02", ".")
              .strip())
        if s:
            sentences.append(s)
    return sentences


def analyze_text(text: str, language: str = "German") -> AnalysisResult:
    from .langdetect import detect_language_scores
    stats = TextStats()
    blocks = split_blocks(text)
    stats.paragraphs = sum(1 for b in blocks if b.kind == "paragraph")
    stats.headings = sum(1 for b in blocks if b.kind == "heading")
    stats.list_items = sum(1 for b in blocks if b.kind == "list_item")
    stats.quotes = sum(1 for b in blocks if b.kind == "quote")
    stats.chapters = sum(1 for b in blocks if b.kind == "heading" and b.level <= 2)

    all_text = "\n".join(b.text for b in blocks)
    stats.chars = len(all_text)
    words = re.findall(r"[^\s]+", all_text)
    stats.words = len(words)
    sentences = split_sentences(all_text)
    stats.sentences = len(sentences)

    stats.numbers = len(re.findall(r"\b\d[\d.,]*\b", all_text))
    stats.years = len(re.findall(r"\b(?:1[5-9]\d{2}|20\d{2}|21\d{2})\b", all_text))
    stats.dates = len(re.findall(
        r"\b\d{1,2}\.\s?\d{1,2}\.(?:\d{2,4})?\b|\b\d{4}-\d{2}-\d{2}\b", all_text))
    stats.times = len(re.findall(r"\b\d{1,2}:\d{2}\b", all_text))
    stats.percentages = len(re.findall(r"\d\s*%", all_text))
    stats.currencies = len(re.findall(r"[€$£]|\bUSD\b|\bEUR\b", all_text))
    stats.abbreviations = len(re.findall(
        r"\b(?:[a-zA-Z]{1,4}\.){1,2}(?=\s|$)", all_text))
    stats.acronyms = len(re.findall(r"\b[A-ZÄÖÜ]{2,6}\b", all_text))
    stats.questions = all_text.count("?")
    stats.exclamations = all_text.count("!")
    stats.quotes_marked = len(re.findall(r"[„\"»]", all_text))

    caps = re.findall(r"\b[A-ZÄÖÜ][a-zäöüß]{2,}(?:-[A-ZÄÖÜ][a-zäöüß]{2,})?\b",
                      all_text)
    stats.names_capitalized = len(caps)
    stats.proper_noun_candidates = sorted(set(caps))[:60]
    stats.technical_terms = sorted(
        {t for t in TECHNICAL_TERMS_DE if t.lower() in all_text.lower()})

    # Fremdwort-Kandidaten (englische Wörter in deutschem Text und umgekehrt)
    foreign = set()
    if language.lower().startswith("ger"):
        for w in re.findall(r"\b[a-zA-Z]{4,}\b", all_text):
            if w[0].isupper() and re.fullmatch(r"[A-Za-z]+", w):
                if w.lower() not in _COMMON_DE_WORDS and len(w) > 4:
                    foreign.add(w)
    stats.foreign_word_candidates = sorted(foreign)[:40]

    # Grobe Atemzeit-Schätzung: deutsches Sprechtempo ~ 14 Zeichen/s
    stats.estimated_seconds = round(stats.chars / 14.0, 1)

    return AnalysisResult(stats=stats, blocks=blocks,
                          language_scores=detect_language_scores(text))


_COMMON_DE_WORDS = set("""der die das und oder nicht ist sind war waren hat
haben wird werden wurde mit von zu zum zur auf für im in am an aus bei nach
über man auch noch nur schon sehr aber dass weil denn wenn als wie so ja nein
kein keine mehr immer wieder zwischen beim durch gegen ohne um eine einer
eines einem diesen diesem diese dieses dort hier dann nun etwa vielleicht
sowie jedoch sowohl als auch nichts etwas alles viele wenige andere gleiche
weil dadurch dadurch damit obwohl während schließlich schließlich""".split())
