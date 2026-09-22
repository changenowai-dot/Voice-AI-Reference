"""Context-aware pauses (Phase 1 + Phase 2 + language profiles).

Pause types: short grammatical, sentence, paragraph, rhetorical,
dramatic, chapter, thought - determined by sentence role, structure
and dramaturgy (NOT only punctuation).

Strategies:
  classic   - Phase-1 behaviour (reference, unchanged)
  semantic  - semantically weighted
  flow      - narrative flow (tighter in-paragraph, clearer boundaries)
  narrative - Prosody/pause optimization for calm long-form narration;
              audible sentence/paragraph/part pauses, small thought
              pauses after comma/semicolon/colon/dash, without
              globally slowing speech rate.

Language support: 'German' (default, historical behaviour) and 'English'
use separate base tables and separate strategy tables via
``.german.PAUSE_BASE_DE/PAUSE_STRATEGIES`` and
``.english.PAUSE_BASE_EN/PAUSE_STRATEGIES_EN``.
"""
from __future__ import annotations

import hashlib
import logging

log = logging.getLogger("voiceover.prosody.pauses")

from . import german as _de
from . import english as _en
from ..segmentation import Segment


def _lang_module(language: str | None):
    """Explizite Sprachwahl der Pausen-Profile.

    DE -> german.py (PAUSE_BASE_DE / PAUSE_STRATEGIES / *_DE-Regler)
    EN -> english.py (PAUSE_BASE_EN / PAUSE_STRATEGIES_EN / *_EN-Regler)
    Unbekannt/leer -> DE (dokumentierter Rueckwaertskompatibilitaets-Fall).
    DE- und EN-Werte teilen sich KEINE Regler: Aenderungen an EN betreffen
    nie DE und umgekehrt.
    """
    if language and language.lower().startswith("en"):
        return _en
    return _de


def _pause_knobs(language: str | None) -> dict:
    """Sprachspezifische Pausen-Regler (STRIKT getrennt DE vs. EN).

    Liest STYLE_FACTOR_*/PAUSE_LIMITS_*/PAUSE_JITTER_* aus dem
    sprachzugehoerigen Modul. Fallback auf die historischen Globalwerte,
    falls ein Modul die Konstanten nicht definiert (z. B. aeltere
    Sprachmodule) – Verhalten damit identisch zum Stand vor der Trennung.
    """
    modu = _lang_module(language)
    return {
        "style_factor": getattr(modu, "STYLE_FACTOR_DE", None)
        or getattr(modu, "STYLE_FACTOR_EN", None) or STYLE_FACTOR,
        "limits": (getattr(modu, "PAUSE_LIMITS_DE", None)
                   or getattr(modu, "PAUSE_LIMITS_EN", None)
                   or {k: (_MIN_PAUSE[k], _MAX_PAUSE[k]) for k in _MIN_PAUSE}),
        "jitter": getattr(modu, "PAUSE_JITTER_DE", None)
        if hasattr(modu, "PAUSE_JITTER_DE")
        else getattr(modu, "PAUSE_JITTER_EN", 0.10),
    }


STYLE_FACTOR = {"tight": 0.72, "auto": 1.0, "relaxed": 1.3}
# Per-strategy soft floors - prevent near-0 ms gaps when jitter+speed
# compound.
_MIN_PAUSE = {"classic": 0.18, "semantic": 0.20, "flow": 0.18,
              "narrative": 0.22}
_MAX_PAUSE = {"classic": 2.40, "semantic": 2.60, "flow": 2.40,
              "narrative": 2.80}


def _jitter(seg: Segment, scale: float = 0.10) -> float:
    """Deterministic, reproducible micro-variation (+/-10 %)."""
    h = int(hashlib.sha256(
        f"{seg.index}:{seg.source_preview}".encode()).hexdigest()[:8], 16)
    frac = ((h % 1000) / 1000.0) * 2.0 - 1.0
    return 1.0 + frac * scale


def base_pause_for(seg: Segment, next_seg: Segment | None,
                   strategy: str = "classic",
                   language: str | None = None) -> float:
    """Base pause duration (seconds) after a segment."""
    modu = _lang_module(language)
    PAUSE_BASE = modu.PAUSE_BASE_EN if language and language.lower().startswith("en") else modu.PAUSE_BASE_DE
    PAUSE_STRATEGIES = modu.PAUSE_STRATEGIES_EN if language and language.lower().startswith("en") else modu.PAUSE_STRATEGIES
    dominant_role = modu.dominant_role
    terminator_role = modu.terminator_role

    mod = PAUSE_STRATEGIES.get(strategy, {})
    role = dominant_role(seg.text)
    term = terminator_role(seg.text)
    if next_seg is None:
        return mod.get("end_of_text", PAUSE_BASE["end_of_text"])
    if next_seg.block_kind == "heading":
        lvl = getattr(next_seg, "heading_level", 3)
        if seg.block_kind == "heading":
            return mod.get("heading_after", PAUSE_BASE["heading_after"])
        ch = mod.get("chapter", PAUSE_BASE["chapter"])
        hd = mod.get("heading", PAUSE_BASE["heading"])
        return ch if lvl <= 2 else hd
    if next_seg.block_kind != seg.block_kind:
        if next_seg.block_kind == "list_item":
            return mod.get("list_item", PAUSE_BASE["list_item"])
        if seg.block_kind == "quote":
            return mod.get("quote_end", PAUSE_BASE["quote_end"])
        para = mod.get("paragraph", PAUSE_BASE["paragraph"])
        return max(para, mod.get("paragraph_min", para)) if mod else para
    if getattr(next_seg, "block_index", None) is not None and \
            next_seg.block_index != getattr(seg, "block_index", None):
        para = mod.get("paragraph", PAUSE_BASE["paragraph"])
        return max(para, mod.get("paragraph_min", para)) if mod else para
    if seg.block_kind == "list_item":
        base = mod.get("in_list", mod.get("list_item",
                                          PAUSE_BASE["list_item"]))
        return base * mod.get("list_factor", 1.0) if mod else base
    # Clause-level (only in narrative): commas/semicolons/colons/dashes/ellipsis
    if strategy == "narrative" and term is not None and \
            role not in ("question", "rhetorical_question"):
        key = {
            "comma": "after_comma",
            "semicolon": "after_semicolon",
            "colon": "after_colon",
            "dash": "after_dash",
            "ellipsis": "after_ellipsis",
            "exclamation": "exclamation",
        }.get(term)
        if key and key in mod:
            return mod[key]
        if term == "exclamation":
            return mod.get("exclamation", PAUSE_BASE.get("emphasis", 0.6))
    # Sentence-role-driven
    base = mod.get(role, PAUSE_BASE.get(role, PAUSE_BASE["statement"]))
    if mod:
        if strategy in ("semantic", "narrative"):
            if role == "rhetorical_question":
                return mod.get("after_rhetorical", base)
            if role == "question":
                return mod.get("after_question", base)
            if role == "dramatic":
                return mod.get("after_dramatic", base)
            if role == "transition":
                return base + mod.get("transition_extra", 0.0)
            if role == "list":
                return base * mod.get("list_factor", 1.0)
        if strategy == "flow":
            if role == "statement":
                return mod.get("statement", base)
            if role == "list":
                return mod.get("in_list", base)
            if role == "rhetorical_question":
                return mod.get("after_rhetorical", base)
    return base


def pause_type(seg: Segment, next_seg: Segment | None,
               language: str | None = None) -> str:
    if next_seg is None:
        return "end_of_text"
    if next_seg.block_kind == "heading":
        lvl = getattr(next_seg, "heading_level", 3)
        if seg.block_kind == "heading":
            return "heading_after"
        return "chapter" if lvl <= 2 else "heading"
    if next_seg.block_kind != seg.block_kind or \
            getattr(next_seg, "block_index", None) not in (None,
                    getattr(seg, "block_index", None)):
        if next_seg.block_kind == "list_item" or seg.block_kind == "list_item":
            return "list_item"
        if seg.block_kind == "quote":
            return "quote_end"
        return "paragraph"
    modu = _lang_module(language)
    return modu.dominant_role(seg.text)


def pause_after(seg: Segment, next_seg: Segment | None, style: str = "auto",
                speed: float = 1.0, strategy: str = "classic",
                pause_profile: dict | None = None,
                language: str | None = None) -> float:
    knobs = _pause_knobs(language)
    factor = knobs["style_factor"].get(style, 1.0)
    speed_adj = 1.0 / max(speed, 0.5) ** 0.5 if speed else 1.0
    base = base_pause_for(seg, next_seg, strategy=strategy, language=language)
    value = base * factor * speed_adj * _jitter(seg, knobs["jitter"])
    lo, hi = knobs["limits"].get(strategy, (0.18, 2.40))
    return round(min(max(value, lo), hi), 3)


def assign_pauses(segments: list[Segment], style: str = "auto",
                  speed: float = 1.0, strategy: str = "classic",
                  pause_profile: dict | None = None,
                  language: str | None = None) -> list[Segment]:
    knobs = _pause_knobs(language)
    lo, hi = knobs["limits"].get(strategy, (0.18, 2.40))
    modu = _lang_module(language)
    log.info(
        "PAUSE_PROFILE_SELECT language=%s tables=%s strategy=%s style=%s "
        "style_factor=%.2f limits=(%.2f, %.2f) jitter=%.2f segments=%d",
        language or "German(default)",
        "EN" if modu is _en else "DE",
        strategy, style, knobs["style_factor"].get(style, 1.0), lo, hi,
        knobs["jitter"], len(segments))
    for i, seg in enumerate(segments):
        nxt = segments[i + 1] if i + 1 < len(segments) else None
        seg.pause_after_s = pause_after(seg, nxt, style=style, speed=speed,
                                        strategy=strategy, language=language)
        if pause_profile:
            role = modu.dominant_role(seg.text)
            if role in pause_profile:
                seg.pause_after_s = round(
                    min(max(pause_profile[role], lo), hi), 3)
        seg.pause_type = pause_type(seg, nxt, language=language)
    return segments
