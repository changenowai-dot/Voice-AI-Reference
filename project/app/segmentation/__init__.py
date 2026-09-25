"""Semantic long-form segmentation.

Design principles
-----------------
- Prefer PARAGRAPH boundaries; never split inside a paragraph if the
  paragraph stays within the target band.
- Prefer SENTENCE boundaries. NEVER split mid-sentence unless a single
  sentence exceeds ``max_chars`` (rare for prose; handled by
  :func:`_split_oversize_sentence` at clause/phrase boundaries).
- Produce segments of roughly ``target_chars``; allow up to
  ``max_chars`` when appending one more sentence keeps a coherent
  thought together.
- Avoid micro-segments (< ``min_chars``) by merging tail fragments with
  the previous segment when safe.
- The original text is NEVER rewritten — sentences are concatenated
  verbatim with a single space (already produced by
  :func:`split_sentences` after abbreviation/number/initials handling).
- Supports duration-oriented presets (30-45s / 60-90s / 90-120s /
  120-180s) via :class:`SegmentationConfig` and
  :func:`preset_by_target_seconds` so benchmarks can sweep segment
  lengths reproducibly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from ..text.analyze import Block, split_sentences


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class Segment:
    index: int
    text: str                        # final TTS text (normalized + pronounced)
    sentence_count: int = 1
    block_kind: str = "paragraph"    # heading | paragraph | list_item | quote
    block_index: int = 0
    heading_level: int = 3
    is_first_in_block: bool = False
    is_last_in_block: bool = False
    next_block_kind: str | None = None
    pause_after_s: float = 0.55       # set by app.prosody.pauses
    pause_type: str = "statement"
    source_preview: str = ""
    chars: int = 0

    def __post_init__(self):
        self.chars = len(self.text)


@dataclass
class SegmentationConfig:
    """Character budgets, mapped 1:1 to approximate speech duration.

    Default ``balanced_semantic`` ≈ 60-90 s (chars_per_sec ≈ 13.8-15
    depending on language). Long-form benchmarks can select presets via
    :func:`preset_by_target_seconds`.
    """
    target_chars: int = 900           # ~60 s @ 15 chars/s — aim to close near here
    min_chars: int = 350              # ~23 s  — avoid micro-segments
    max_chars: int = 1500             # ~100 s — hard cap
    # How aggressively to close segments:
    #   0.0 -> only close when adding the next sentence would exceed max
    #   1.0 -> close as soon as we reach target_chars
    # Intermediate values permit pulling in one more sentence up to
    # target + close_slack*target so a final connector/clause doesn't
    # become its own micro-segment.
    close_slack: float = 0.45
    allow_tail_merge: bool = True
    hard_start_min_chars: int = 200
    respect_paragraph_boundary: bool = True


# Presets for the benchmark sweep. chars_per_sec is intentionally a
# conservative lower bound to avoid OOM when speakers speak slightly
# slower than average.
_PRESETS: dict[str, dict] = {
    "short_30_45":   {"target_chars":  500, "min_chars": 200, "max_chars":  750},
    "balanced_60_90":{"target_chars":  900, "min_chars": 400, "max_chars": 1400},
    "long_90_120":   {"target_chars": 1400, "min_chars": 600, "max_chars": 1900},
    "xl_120_180":    {"target_chars": 2000, "min_chars": 900, "max_chars": 2700},
    "adaptive_180":  {"target_chars": 1200, "min_chars": 350, "max_chars": 2700},
}


def preset_by_target_seconds(label: str,
                             chars_per_sec: float = 14.5) -> SegmentationConfig:
    """Return a config for one of the named presets.

    ``chars_per_sec`` scales the char budgets; use 13.8 for German /
    15.0 for English if you want language-specific scaling.
    """
    key = label.lower().replace(" ", "_").replace("-", "_")
    if key not in _PRESETS:
        # Fallback: interpret "30-45"/"60-90"/"90-120"/"120-180"/"adaptive"
        if "-" in label:
            lo, hi = label.split("-", 1)
            try:
                los, his = float(lo), float(hi)
                target_s = (los + his) / 2.0
                return SegmentationConfig(
                    target_chars=int(target_s * chars_per_sec),
                    min_chars=int(los * 0.6 * chars_per_sec),
                    max_chars=int(his * 1.05 * chars_per_sec),
                )
            except ValueError:
                pass
        raise ValueError(f"unknown segmentation preset: {label!r}")
    base = dict(_PRESETS[key])
    if chars_per_sec and abs(chars_per_sec - 14.5) > 0.01:
        scale = chars_per_sec / 14.5
        base = {k: int(v * scale) for k, v in base.items()}
    return SegmentationConfig(**base)


# ---------------------------------------------------------------------------
# Sentence splitting helpers
# ---------------------------------------------------------------------------
_CLAUSE_SPLIT_STRONG = re.compile(r"(?<=[;:…—–])\s+")
_CLAUSE_SPLIT_COMMA = re.compile(r"(?<=,)\s+")
# Nebensatz-/Koordinationsgrenzen fuer Saetze OHNE Kommas/Strichpunkte.
# Zero-Width-Split vor dem Konnektor: der Konnektor bleibt am Anfang des
# Nachfolge-Chunks, der Text bleibt byte-identisch (nur Whitespace kollabiert
# zu einem Leerzeichen). Nur die letzte Rettung vor dem Wortfallback.
_CLAUSE_SPLIT_COORD = re.compile(
    r"(?<=[a-zäöüß])\s+(?=(?:und|oder|aber|sondern|sowie|beziehungsweise|"
    r"bzw|and|but|or|yet)\s)", re.IGNORECASE)
_WORD_SPLIT = re.compile(r"\s+")


def _split_oversize_sentence(sentence: str, max_chars: int) -> list[str]:
    """Split a single over-long sentence at clause/phrase/word boundaries.

    Tries in order: strong clause punctuation (``; : … — –``), commas,
    word boundaries. Never splits inside a word.
    """
    if len(sentence) <= max_chars:
        return [sentence]
    parts = _CLAUSE_SPLIT_STRONG.split(sentence)
    if len(parts) > 1 and all(len(p) <= max_chars for p in parts):
        return [p.strip() for p in parts if p.strip()]
    if len(parts) > 1:
        # combine parts greedily up to max_chars
        chunks = _greedy_accumulate(parts, max_chars, sep=" ")
        if all(len(c) <= max_chars for c in chunks):
            return chunks
    parts = _CLAUSE_SPLIT_COMMA.split(sentence)
    if len(parts) > 1:
        chunks = _greedy_accumulate(parts, max_chars, sep=" ")
        chunks = _merge_tiny_tails(chunks, max_chars, min_len=60)
        return chunks
    # Koordinationsgrenzen ("... Jung | und in die Quantenwelten ..."):
    # Fuer kommalose Saetze deutlich besser als ein Schnitt an beliebiger
    # Wortgrenze. Stresstext-Fall: 203-Zeichen-Satz ohne ein Komma endete
    # vorher mit 1-Wort-Orphan ("gereist." als 8-Zeichen-Einzelsegment) und
    # einem Phrase-mitten-Schnitt vor dem letzten Wort.
    parts = _CLAUSE_SPLIT_COORD.split(sentence)
    if len(parts) > 1:
        chunks = _greedy_accumulate(parts, max_chars, sep=" ")
        chunks = _merge_tiny_tails(chunks, max_chars, min_len=60)
        if len(chunks) > 1 and all(len(c) <= max_chars for c in chunks):
            return chunks
    words = _WORD_SPLIT.split(sentence)
    chunks = _greedy_accumulate(words, max_chars, sep=" ")
    chunks = _merge_tiny_tails(chunks, max_chars, min_len=60)
    return _rebalance_tiny_tail(chunks, max_chars)


def _rebalance_tiny_tail(chunks: list[str], max_chars: int,
                         min_words: int = 2) -> list[str]:
    """Verschiebt Schlusswoerter vom vorletzten in den letzten Chunk, bis der
    letzte Chunk mindestens ``min_words`` Woerter hat (der vorletzte wird nur
    kuerzer, bleibt also innerhalb ``max_chars``).

    Verhindert 1-Wort-Orphan-Segmente, wenn selbst der Koordinations-Split
    nicht greift (Satz ohne Kommas UND ohne Konnektoren) und
    ``_merge_tiny_tails`` wegen ``max_chars`` nicht mehr zusammenfuehren kann.
    """
    if len(chunks) < 2:
        return chunks
    merged = list(chunks)
    tail = merged[-1]
    while len(tail.split()) < min_words:
        prev_words = merged[-2].split()
        if len(prev_words) <= min_words:
            break
        moved = prev_words.pop()
        merged[-2] = " ".join(prev_words)
        tail = f"{moved} {tail}".strip()
    merged[-1] = tail
    return merged


def _greedy_accumulate(parts: Iterable[str], max_chars: int, sep: str = " ") -> list[str]:
    out: list[str] = []
    buf = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        cand = (buf + sep + p).strip() if buf else p
        if len(cand) > max_chars and buf:
            out.append(buf)
            buf = p
        else:
            buf = cand
    if buf:
        out.append(buf)
    return out


def _merge_tiny_tails(chunks: list[str], max_chars: int,
                      min_len: int = 80) -> list[str]:
    """Merge chunks shorter than ``min_len`` into their neighbour when
    the result fits within ``max_chars`` to avoid staccato tail pieces.

    BEHOBENER BUG: Beide Merge-Pfade endeten auf ``.rstrip(",;:")``. Das
    loeschte das Klauselzeichen am Ende des zusammengefuehrten Chunks –
    nachweisbar Satzzeichenverlust (Direkttest: 3 Kommata rein, 1 Komma
    raus). Seit Klausel-Trennung im Produktionspfad tatsaechlich greift
    (siehe ``_group_items``) ist das relevant: ein Chunk, der auf ``,``
    endet, ist genau der Fall, fuer den die ``narrative``-Strategie
    ``after_comma`` vorsieht. Das Satzzeichen muss erhalten bleiben –
    entfernt wird nur Leerraum.
    """
    if len(chunks) <= 1:
        return chunks
    merged: list[str] = list(chunks)
    # forward pass: merge tiny heads
    i = 0
    while i < len(merged) - 1:
        if len(merged[i]) < min_len and len(merged[i]) + 1 + len(merged[i+1]) <= max_chars:
            merged[i] = (merged[i] + " " + merged[i+1]).strip()
            del merged[i+1]
        else:
            i += 1
    # backward pass: merge tiny tails
    i = len(merged) - 1
    while i > 0:
        if len(merged[i]) < min_len and len(merged[i-1]) + 1 + len(merged[i]) <= max_chars:
            merged[i-1] = (merged[i-1] + " " + merged[i]).strip()
            del merged[i]
        i -= 1
    return merged


# ---------------------------------------------------------------------------
# Sentence grouping into segments
# ---------------------------------------------------------------------------
def _group_sentences(sentences: list[str], cfg: SegmentationConfig) -> list[list[str]]:
    """Greedy sentence grouping.

    Strategy:
      1. Append sentences until adding the next one would exceed
         ``max_chars``; flush.
      2. Additionally flush after appending a sentence that ends with a
         terminator (``.!?…``) once the buffer is past ``target_chars``
         AND past ``hard_start_min_chars``. We accept overshoot up to
         ``target * (1 + close_slack)`` so a natural tail sentence
         doesn't become its own micro-segment.
    """
    groups: list[list[str]] = []
    buf: list[str] = []

    def _len(b: list[str]) -> int:
        return sum(len(x) + 1 for x in b) - 1 if b else 0

    def flush():
        nonlocal buf
        if buf:
            groups.append(buf)
            buf = []

    def _is_closer(sent: str) -> bool:
        s = sent.rstrip().rstrip("\"'”»)")
        return bool(s) and s[-1] in ".!?…"

    close_threshold = int(cfg.target_chars * (1.0 + cfg.close_slack))

    for s in sentences:
        s = s.strip()
        if not s:
            continue
        slen = len(s)
        if slen > cfg.max_chars:
            flush()
            for piece in _split_oversize_sentence(s, cfg.max_chars):
                groups.append([piece])
            continue
        cur = _len(buf)
        new_len = cur + (1 if cur else 0) + slen
        if buf and new_len > cfg.max_chars:
            flush()
            new_len = slen
        buf.append(s)
        after = _len(buf)
        if (after >= cfg.target_chars
                and after >= cfg.hard_start_min_chars
                and after <= close_threshold
                and _is_closer(s)):
            flush()
    flush()
    if cfg.allow_tail_merge:
        # Backward merge tiny tails
        i = len(groups) - 1
        while i > 0:
            pl = _len(groups[i-1]); cl = _len(groups[i])
            if cl < cfg.min_chars and pl + 1 + cl <= cfg.max_chars:
                groups[i-1] = groups[i-1] + groups[i]
                groups.pop(i)
            i -= 1
        # Forward merge tiny heads
        if len(groups) >= 2:
            fl = _len(groups[0]); nl = _len(groups[1])
            if fl < cfg.min_chars and fl + 1 + nl <= cfg.max_chars:
                groups[1] = groups[0] + groups[1]
                groups.pop(0)
    return groups


def _group_items(items: list[tuple[str, int, object]],
                 cfg: SegmentationConfig) -> list[list[tuple[str, int, object]]]:
    """Greedy grouping of ``(sentence, block_index, block)`` ITEMS.

    Exakt dieselbe Strategie wie :func:`_group_sentences`, aber die
    Block-Metadaten reisen mit jedem Satz mit. Das ist noetig, weil
    :func:`_split_oversize_sentence` aus EINEM Quellssatz mehrere Gruppen
    machen kann.

    BEHOBENER BUG: ``segment_text`` bildete Gruppen bisher positionell auf
    die Quell-Items ab::

        item_groups.append(block_items[pos:pos + len(g)])
        pos += len(g)

    Das setzt voraus, dass ein Gruppen-Element genau einem Quell-Satz
    entspricht. Sobald ein ueberslanger Satz geteilt wurde, entstanden mehr
    Gruppen-Elemente als Quell-Items – die Abbildung driftete. Messbare
    Folgen bei einem 349-Zeichen-Satz mit ``max_chars=330``:

      * die Split-Teile wurden verworfen, der UNGETEILTE Originalsatz
        landete im Segment (349 > 330: ``max_chars`` verletzt),
      * ``_split_oversize_sentence`` war damit im Produktionspfad
        wirkungslos, und die Klausel-Pausen der ``narrative``-Strategie
        (``after_comma``/``after_semicolon``/``after_colon``/``after_dash``/
        ``after_ellipsis``) waren unerreichbar,
      * die ueberzaehligen Gruppen griffen hinter das Listenende und
        erzeugten LEERE Segmente (0 Zeichen, 0 Saetze), die die Pipeline
        ungefiltert zur Synthese geschickt haette.

    Geteilte Teile erben hier die Metadaten ihres Ursprungs-Items, damit
    Block-/Absatz-Information und Pausentyp korrekt bleiben.
    """
    groups: list[list[tuple[str, int, object]]] = []
    buf: list[tuple[str, int, object]] = []

    def _len(b: list[tuple[str, int, object]]) -> int:
        return sum(len(x[0]) + 1 for x in b) - 1 if b else 0

    def flush() -> None:
        nonlocal buf
        if buf:
            groups.append(buf)
            buf = []

    def _is_closer(sent: str) -> bool:
        s = sent.rstrip().rstrip("\"'\u201d\u00bb")
        return bool(s) and s[-1] in ".!?\u2026"

    close_threshold = int(cfg.target_chars * (1.0 + cfg.close_slack))

    for sent, bi, block in items:
        s = sent.strip()
        if not s:
            continue
        slen = len(s)
        if slen > cfg.max_chars:
            flush()
            # Jedes Split-Stueck wird eine EIGENE Gruppe und erbt (bi, block).
            for piece in _split_oversize_sentence(s, cfg.max_chars):
                piece = piece.strip()
                if piece:
                    groups.append([(piece, bi, block)])
            continue
        cur = _len(buf)
        new_len = cur + (1 if cur else 0) + slen
        if buf and new_len > cfg.max_chars:
            flush()
        buf.append((s, bi, block))
        after = _len(buf)
        if (after >= cfg.target_chars
                and after >= cfg.hard_start_min_chars
                and after <= close_threshold
                and _is_closer(s)):
            flush()
    flush()

    if cfg.allow_tail_merge:
        # Rueckwaerts: winzige Tails in den Vorgaenger ziehen
        i = len(groups) - 1
        while i > 0:
            pl = _len(groups[i - 1])
            cl = _len(groups[i])
            if cl < cfg.min_chars and pl + 1 + cl <= cfg.max_chars:
                groups[i - 1] = groups[i - 1] + groups[i]
                groups.pop(i)
            i -= 1
        # Vorwaerts: winzigen Kopf in den Nachfolger ziehen
        if len(groups) >= 2:
            fl = _len(groups[0])
            nl = _len(groups[1])
            if fl < cfg.min_chars and fl + 1 + nl <= cfg.max_chars:
                groups[1] = groups[0] + groups[1]
                groups.pop(0)
    return groups


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def segment_text(blocks: list[Block], tts_text_provider,
                 cfg: SegmentationConfig | None = None) -> list[Segment]:
    """Produce a list of :class:`Segment` from block-structured text.

    ``tts_text_provider(block) -> str`` must return the
    normalized+pronunciation-corrected TTS text for a block. Sentence
    splitting is done on that text so every segment is a complete
    sentence (or sequence of complete sentences). The structural block
    metadata is preserved for pause assignment downstream.

    Die Gruppierung laeuft ueber :func:`_group_items`, d. h. Saetze UND
    ihre Block-Metadaten werden gemeinsam gruppiert. Beide Zweige
    (mit und ohne Absatzgrenze) nutzen denselben Pfad; eine positionelle
    Rueckabbildung ``block_items[pos:pos+len(g)]`` gibt es nicht mehr,
    weil sie driftete, sobald ein Satz geteilt wurde (Split-Teile
    verworfen, ``max_chars`` verletzt, leere Segmente).
    """
    cfg = cfg or SegmentationConfig()
    segments: list[Segment] = []
    idx = 0

    # Collect sentences per block, tracking which block each came from.
    # If respect_paragraph_boundary is False, we concatenate sentences
    # across block boundaries into one stream and let the target/max
    # limits decide breakpoints (useful for benchmark presets with long
    # targets on dense prose).
    all_items: list[tuple[str, int, Block]] = []   # (sentence, block_index, block)
    for bi, block in enumerate(blocks):
        tts_text = tts_text_provider(block)
        if not tts_text or not tts_text.strip():
            continue
        for raw_line in re.split(r"\n+", tts_text.strip()):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            for s in split_sentences(raw_line) or [raw_line]:
                s = s.strip()
                if s:
                    all_items.append((s, bi, block))

    def _emit_group(group, is_first: bool, is_last: bool, next_kind) -> None:
        """Erzeugt ein Segment aus einer Item-Gruppe.

        Die Metadaten stammen aus den Items selbst und nicht aus einer
        positionellen Rueckabbildung. Dadurch bleiben Block-Zugehoerigkeit,
        ``heading_level`` und Pausentyp auch fuer geteilte Saetze korrekt.
        Leere Gruppen/Texte werden defensiv verworfen, damit nie ein
        0-Zeichen-Segment in die Synthese geht.
        """
        nonlocal idx
        if not group:
            return
        text = " ".join(s for s, _, _ in group).strip()
        if not text:
            return
        first_bi = group[0][1]
        first_block = blocks[first_bi]
        segments.append(Segment(
            index=idx, text=text, sentence_count=len(group),
            block_kind=first_block.kind, block_index=first_bi,
            heading_level=(first_block.level
                           if first_block.kind == "heading" else 3),
            is_first_in_block=is_first,
            is_last_in_block=is_last,
            next_block_kind=(next_kind if next_kind is not None
                             else first_block.kind),
            source_preview=text[:80],
        ))
        idx += 1

    if cfg.respect_paragraph_boundary:
        # Pro Block gruppieren – die Absatzgrenze bleibt immer erhalten.
        for bi, block in enumerate(blocks):
            block_items = [it for it in all_items if it[1] == bi]
            if not block_items:
                continue
            groups = [g for g in _group_items(block_items, cfg) if g]
            if not groups:
                continue
            next_block = blocks[bi + 1].kind if bi + 1 < len(blocks) else None
            for gi, group in enumerate(groups):
                is_last = (gi == len(groups) - 1)
                _emit_group(group, is_first=(gi == 0), is_last=is_last,
                            next_kind=next_block if is_last else block.kind)
    else:
        # Absatzuebergreifend: EIN Satzstrom, target/max entscheiden die
        # Grenzen. is_first/is_last ergeben sich aus dem Blockwechsel
        # zwischen benachbarten Gruppen (semantisch korrekt statt
        # pauschal ueber block.kind).
        groups = [g for g in _group_items(all_items, cfg) if g]
        for gi, group in enumerate(groups):
            first_bi = group[0][1]
            last_bi = group[-1][1]
            prev_last_bi = groups[gi - 1][-1][1] if gi > 0 else None
            next_first_bi = (groups[gi + 1][0][1]
                             if gi + 1 < len(groups) else None)
            next_block = (blocks[last_bi + 1].kind
                          if last_bi + 1 < len(blocks) else None)
            _emit_group(group,
                        is_first=(first_bi != prev_last_bi),
                        is_last=(last_bi != next_first_bi),
                        next_kind=next_block)
    return segments


__all__ = ["Segment", "SegmentationConfig", "segment_text",
           "preset_by_target_seconds"]
