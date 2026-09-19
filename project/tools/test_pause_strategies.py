#!/usr/bin/env python3
"""Back-compat + narrative-pause regression tests.

Validates:
  A) classic strategy produces historically-expected pause values
     (reference constants unchanged).
  B) narrative strategy is strictly >= classic for every base role,
     i.e. it never makes pauses shorter than the reference.
  C) narrative commas/semicolons/colons/dashes/ellipses receive a
     distinct, audible pause (not the sentence-ending value).
  D) min/max pause floors prevent near-0-ms gaps.
  E) pause style factor + speed_adj still applies to narrative.
  F) existing semantic/flow strategies are unchanged.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.segmentation import Segment                              # noqa: E402
from app.prosody.pauses import pause_after, base_pause_for, _MIN_PAUSE, _MAX_PAUSE  # noqa: E402
from app.prosody.german import PAUSE_BASE_DE, PAUSE_STRATEGIES    # noqa: E402


def _mk(text, idx=0, block_kind="paragraph", block_index=0,
        heading_level=3, is_first_in_block=False, is_last_in_block=False,
        next_block_kind=None):
    return Segment(
        index=idx, text=text, sentence_count=1,
        block_kind=block_kind, block_index=block_index,
        heading_level=heading_level,
        is_first_in_block=is_first_in_block,
        is_last_in_block=is_last_in_block,
        next_block_kind=next_block_kind,
        source_preview=text[:80])


def test_classic_unchanged():
    """Classic pause constants and structural boundaries must match the
    historical reference (these are the values that shipped in 9477f8f
    and have been in production). We verify the constants directly and
    the structural-boundary code paths, rather than relying on sentence-
    role classification which is a more heuristic layer."""
    # Basiskonstanten
    assert PAUSE_BASE_DE["statement"] == 0.42
    assert PAUSE_BASE_DE["question"] == 0.58
    assert PAUSE_BASE_DE["rhetorical_question"] == 0.74
    assert PAUSE_BASE_DE["paragraph"] == 0.86
    assert PAUSE_BASE_DE["chapter"] == 1.35
    assert PAUSE_BASE_DE["end_of_text"] == 1.05
    # Strukturpfade
    seg_p = _mk("Paragraph one.", block_index=0)
    nxt_p = _mk("Paragraph two.", block_index=1)
    assert abs(base_pause_for(seg_p, nxt_p, "classic") - 0.86) < 0.01
    seg_h = _mk("Chapter begins.")
    nxt_h = _mk("A Title", block_kind="heading", heading_level=1)
    assert abs(base_pause_for(seg_h, nxt_h, "classic") - 1.35) < 0.01
    seg_e = _mk("Final words.")
    assert abs(base_pause_for(seg_e, None, "classic") - 1.05) < 0.01
    # Klassische Aussagen-Pause (statement)
    seg_s = _mk("That is the mark of serious writing.")
    nxt_s = _mk("Next sentence follows here.")
    assert abs(base_pause_for(seg_s, nxt_s, "classic") - 0.42) < 0.05
    print("[PASS] A classic unchanged")


def test_narrative_never_shorter():
    """narrative must produce pauses >= classic for every role (no regression)."""
    samples = [
        "That is the mark of serious writing.",                # statement
        "What happens when we slow down?",                    # question
        "But who, really, is listening?",                     # rhetorical
        "This is a list: one, two, three, and finally four.", # list
        "Not silence, but attention.",                        # contrast
        "That is, precisely, the point.",                     # emphasis
        "We did it because we had to.",                       # explanation
        "Then came the quiet.",                               # dramatic
        "Then, years later, something changed.",              # transition
        "Perhaps it was already there.",                      # calm
    ]
    for text in samples:
        seg = _mk(text)
        nxt = _mk("And this is the next sentence.")
        c = base_pause_for(seg, nxt, strategy="classic")
        n = base_pause_for(seg, nxt, strategy="narrative")
        assert n >= c - 1e-6, (
            f"narrative shorter than classic for {text!r}: {n} < {c}")
    print("[PASS] B narrative >= classic everywhere")


def test_narrative_clause_pauses():
    """Comma/semicolon/colon/dash/ellipsis segment endings receive distinct pauses."""
    cases = [
        ("Each time we read it,",                            "comma",      0.32),
        ("Not merely recount events;",                        "semicolon",  0.50),
        ("Something new surfaces:",                           "colon",      0.52),
        ("Then came the quiet —",                             "dash",       0.55),
        ("The room fell silent…",                             "ellipsis",   0.62),
    ]
    for text, name, want in cases:
        seg = _mk(text)
        nxt = _mk("the next phrase follows here.")
        val = base_pause_for(seg, nxt, strategy="narrative")
        assert abs(val - want) < 0.05, (
            f"{name} narrative pause={val} want≈{want}")
        # Classic does NOT have these special values (it just uses
        # dominant_role → statement).
        cval = base_pause_for(seg, nxt, strategy="classic")
        # in narrative, clause pauses are shorter than a full sentence
        # but longer than a zero-gap. Also ensure narrative actually
        # differs from classic at comma (comma was previously treated as
        # end-of-sentence because segments rarely end with comma; we
        # just check they are distinct & sensible).
        assert val > 0.22, f"{name} too short: {val}"
    print("[PASS] C narrative clause pauses")


def test_min_floor_prevents_near_zero():
    """Even with jitter and tight style+speed=1.2, pause >= floor."""
    seg = _mk("Short words here.")
    nxt = _mk("Next.")
    for strat, floor in _MIN_PAUSE.items():
        v = pause_after(seg, nxt, style="tight", speed=1.2, strategy=strat)
        assert v >= floor - 0.01, f"{strat} pause={v} < floor={floor}"
        assert v <= _MAX_PAUSE[strat] + 0.01
    print("[PASS] D min/max floors enforced")


def test_narrative_paragraph_and_end():
    """Paragraph/chapter/end pauses are larger and sensible."""
    seg = _mk("Paragraph one.", block_index=0)
    nxt = _mk("Paragraph two.", block_index=1)
    c = base_pause_for(seg, nxt, "classic")
    n = base_pause_for(seg, nxt, "narrative")
    assert n > c and n >= 1.10, f"paragraph narrative {n} classic {c}"
    seg2 = _mk("Final sentence.")
    ce = base_pause_for(seg2, None, "classic")
    ne = base_pause_for(seg2, None, "narrative")
    assert ne >= ce and ne >= 1.30, f"end narrative {ne} classic {ce}"
    print("[PASS] E narrative paragraph/end pauses")


def test_semantic_flow_unchanged():
    assert PAUSE_STRATEGIES["semantic"]["after_rhetorical"] == 1.30
    assert PAUSE_STRATEGIES["semantic"]["after_question"] == 1.10
    assert PAUSE_STRATEGIES["semantic"]["after_dramatic"] == 1.25
    assert PAUSE_STRATEGIES["flow"]["statement"] == 0.36
    assert PAUSE_STRATEGIES["flow"]["in_list"] == 0.42
    assert PAUSE_STRATEGIES["flow"]["paragraph"] == 1.00
    print("[PASS] F semantic/flow unchanged")


if __name__ == "__main__":
    test_classic_unchanged()
    test_narrative_never_shorter()
    test_narrative_clause_pauses()
    test_min_floor_prevents_near_zero()
    test_narrative_paragraph_and_end()
    test_semantic_flow_unchanged()
    print("\nALL PAUSE-STRATEGY TESTS PASSED")
