"""Intelligente Long-Form-Segmentierung (Anforderung 15 + 16).

Bildet Segmente aus ganzen Sätzen, respektiert Absatz-/Kapitelgrenzen,
teilt möglichst nie mitten im Satz und schneidet niemals Wörter ab.
Einzelne Sätze länger als das Maximum werden an Nebensatzgrenzen
(Komma, Semikolon, Gedankenstrich) getrennt.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..text.analyze import Block, split_sentences


@dataclass
class Segment:
    index: int
    text: str                    # fertiger TTS-Text (normalisiert + Aussprache)
    sentence_count: int = 1
    block_kind: str = "paragraph"   # heading | paragraph | list_item | quote
    block_index: int = 0
    heading_level: int = 3
    is_first_in_block: bool = False
    is_last_in_block: bool = False
    next_block_kind: str | None = None
    pause_after_s: float = 0.55    # gesetzt von app.prosody.pauses
    pause_type: str = "statement"  # Pausentyp (Phase 1, Anforderung 14)
    source_preview: str = ""
    chars: int = 0

    def __post_init__(self):
        self.chars = len(self.text)


@dataclass
class SegmentationConfig:
    target_chars: int = 420
    min_chars: int = 120
    max_chars: int = 700


def _split_long_sentence(sentence: str, max_chars: int) -> list[str]:
    """Teilt einen überlangen Satz an Nebensatzgrenzen; nie mitten im Wort."""
    if len(sentence) <= max_chars:
        return [sentence]
    # 1) Versuch: Semikolon / Doppelpunkt / Gedankenstrich
    parts = re.split(r"(?<=[;:–—])\s+", sentence)
    if len(parts) > 1 and all(len(p) <= max_chars for p in parts):
        return [p.strip() for p in parts if p.strip()]
    # 2) Versuch: Kommas
    parts = re.split(r"(?<=,)\s+", sentence)
    if len(parts) > 1:
        chunks: list[str] = []
        buf = ""
        for p in parts:
            cand = (buf + " " + p).strip() if buf else p
            if len(cand) > max_chars and buf:
                chunks.append(buf)
                buf = p
            else:
                buf = cand
        if buf:
            chunks.append(buf)
        # sehr kurze Reste zusammenführen
        merged: list[str] = []
        for c in chunks:
            if merged and len(c) < 40 and len(merged[-1]) + len(c) + 1 <= max_chars:
                merged[-1] = merged[-1].rstrip(",;:") + ", " + c
            else:
                merged.append(c)
        return merged
    # 3) Notfall: Wortgrenze
    words = sentence.split()
    chunks = []
    buf = ""
    for w in words:
        cand = (buf + " " + w).strip() if buf else w
        if len(cand) > max_chars and buf:
            chunks.append(buf)
            buf = w
        else:
            buf = cand
    if buf:
        chunks.append(buf)
    return chunks


def _merge_sentences(sentences: list[str], cfg: SegmentationConfig) -> list[list[str]]:
    """Fasst Sätze zu Segmenten zusammen, bis Zielgröße (annähernd) erreicht."""
    groups: list[list[str]] = []
    buf: list[str] = []
    buf_len = 0
    for s in sentences:
        slen = len(s)
        # Überlänge einzeln behandeln
        if slen > cfg.max_chars:
            if buf:
                groups.append(buf)
                buf, buf_len = [], 0
            for piece in _split_long_sentence(s, cfg.max_chars):
                groups.append([piece])
            continue
        if buf and buf_len + slen + 1 > cfg.target_chars:
            groups.append(buf)
            buf, buf_len = [], 0
        # sehr kurze Sätze niemals allein lassen (außer am Blockende)
        buf.append(s)
        buf_len += slen + 1
    if buf:
        groups.append(buf)
    # Letztes Mini-Segment mit Vorletztem verschmelzen, wenn möglich
    if (len(groups) >= 2 and sum(len(s) for s in groups[-1]) < cfg.min_chars
            and sum(len(s) for s in groups[-2]) +
            sum(len(s) for s in groups[-1]) + 1 <= cfg.max_chars):
        groups[-2] = groups[-2] + groups[-1]
        groups.pop()
    return groups


def segment_text(blocks: list[Block], tts_text_provider, cfg: SegmentationConfig | None = None) -> list[Segment]:
    """Bildet Segmente aus Blöcken.

    tts_text_provider(block) -> bereits normalisierter + aussprache-
    korrigierter Text des Blocks (String). Die Segmentierung arbeitet auf
    der TTS-Version, behält aber die Blockstruktur für Pausen bei.
    """
    cfg = cfg or SegmentationConfig()
    segments: list[Segment] = []
    idx = 0
    for bi, block in enumerate(blocks):
        tts_text = tts_text_provider(block)
        if not tts_text or not tts_text.strip():
            continue
        next_block = blocks[bi + 1].kind if bi + 1 < len(blocks) else None
        # Block in Sätze -> Gruppen
        sentences = []
        for raw in re.split(r"\n+", tts_text.strip()):
            sentences.extend(split_sentences(raw) or [raw.strip()])
        sentences = [s for s in sentences if s and s.strip()]
        groups = _merge_sentences(sentences, cfg)
        for gi, group in enumerate(groups):
            text = " ".join(group)
            segments.append(Segment(
                index=idx,
                text=text,
                sentence_count=len(group),
                block_kind=block.kind,
                block_index=bi,
                heading_level=(block.level if block.kind == "heading" else 3),
                is_first_in_block=(gi == 0),
                is_last_in_block=(gi == len(groups) - 1),
                next_block_kind=next_block if gi == len(groups) - 1 else block.kind,
                source_preview=text[:80],
            ))
            idx += 1
    return segments
