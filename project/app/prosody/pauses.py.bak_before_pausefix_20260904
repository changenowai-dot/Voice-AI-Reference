"""Kontextabhängige Pausen (Phase 1 + Phase 2).

Pausentypen (§14): kurze grammatikalische Pause, Satzpause, Absatzpause,
rhetorische Pause, dramatische Pause, Kapitelpause, Gedankepause –
bestimmt aus Satzrolle, Struktur und Dramaturgie (nicht nur Satzzeichen).

Phase 2 (§10): testbare Pausenstrategien
  classic  – Phase-1-Verhalten (Referenz)
  semantic – semantisch gewichtet (mehr Raum nach Fragen, Atmung bei
             Transitionen, fester Fluss in Aufzählungen)
  flow     – Erzählfluss (knapper im Absatz, deutlicher an Grenzen)
"""
from __future__ import annotations

import hashlib

from ..segmentation import Segment
from .german import PAUSE_BASE_DE, PAUSE_STRATEGIES, dominant_role, \
    profile_sentence

STYLE_FACTOR = {"tight": 0.72, "auto": 1.0, "relaxed": 1.3}


def _jitter(seg: Segment, scale: float = 0.10) -> float:
    """Deterministische, reproduzierbare Kleinstvariation (±10 %)."""
    h = int(hashlib.sha256(
        f"{seg.index}:{seg.source_preview}".encode()).hexdigest()[:8], 16)
    frac = ((h % 1000) / 1000.0) * 2.0 - 1.0     # -1..1
    return 1.0 + frac * scale


def base_pause_for(seg: Segment, next_seg: Segment | None,
                   strategy: str = "classic") -> float:
    """Basis-Pausendauer (Sekunden) nach Pausentyp + Strategie."""
    mod = PAUSE_STRATEGIES.get(strategy, {})
    role = dominant_role(seg.text)
    if next_seg is None:
        return PAUSE_BASE_DE["end_of_text"]
    if next_seg.block_kind == "heading":
        lvl = getattr(next_seg, "heading_level", 3)
        if seg.block_kind == "heading":
            return PAUSE_BASE_DE["heading_after"]
        return PAUSE_BASE_DE["chapter"] if lvl <= 2 else \
            PAUSE_BASE_DE["heading"]
    if next_seg.block_kind != seg.block_kind:
        if next_seg.block_kind == "list_item":
            return PAUSE_BASE_DE["list_item"]
        if seg.block_kind == "quote":
            return PAUSE_BASE_DE["quote_end"]
        base = PAUSE_BASE_DE["paragraph"]
        return max(base, mod.get("paragraph_min", base)) if mod else base
    if getattr(next_seg, "block_index", None) is not None and \
            next_seg.block_index != getattr(seg, "block_index", None):
        base = PAUSE_BASE_DE["paragraph"]              # Absatzgrenze
        return max(base, mod.get("paragraph_min", base)) if mod else base
    if seg.block_kind == "list_item":
        base = PAUSE_BASE_DE["list_item"]
        return base * mod.get("list_factor", 1.0) if mod else base
    # Satzrolle bestimmt die Satzpause danach
    base = PAUSE_BASE_DE.get(role, PAUSE_BASE_DE["statement"])
    if mod:
        if strategy == "semantic":
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


def pause_type(seg: Segment, next_seg: Segment | None) -> str:
    """Name des Pausentyps (für Berichte/Logs)."""
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
    return dominant_role(seg.text)


def pause_after(seg: Segment, next_seg: Segment | None, style: str = "auto",
                speed: float = 1.0, strategy: str = "classic") -> float:
    """Berechnet die Stille nach einem Segment in Sekunden."""
    factor = STYLE_FACTOR.get(style, 1.0)
    # Tempo beeinflusst Pausen mit (schneller gesprochen -> knappere Pausen)
    speed_adj = 1.0 / max(speed, 0.5) ** 0.5 if speed else 1.0
    base = base_pause_for(seg, next_seg, strategy=strategy)
    value = base * factor * speed_adj * _jitter(seg)
    # Sanfte Begrenzung (keine Übertreibung, §14)
    return round(min(max(value, 0.18), 2.4), 3)


def assign_pauses(segments: list[Segment], style: str = "auto",
                  speed: float = 1.0, strategy: str = "classic",
                  pause_profile: dict | None = None) -> list[Segment]:
    """Setzt Pausen; pause_profile erlaubt Overrides aus dem A/B-Test."""
    for i, seg in enumerate(segments):
        nxt = segments[i + 1] if i + 1 < len(segments) else None
        seg.pause_after_s = pause_after(seg, nxt, style=style, speed=speed,
                                        strategy=strategy)
        if pause_profile:
            role = dominant_role(seg.text)
            if role in pause_profile:
                seg.pause_after_s = round(min(max(
                    pause_profile[role], 0.18), 2.4), 3)
        seg.pause_type = pause_type(seg, nxt)
    return segments
