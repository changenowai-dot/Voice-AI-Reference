"""Offline-Pausen-/Prosodie-Regression (kein TTS nötig)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.segmentation import Segment, SegmentationConfig, segment_text  # noqa: E402
from app.prosody.pauses import assign_pauses  # noqa: E402
from app.text.analyze import analyze_text  # noqa: E402


def _segs(text: str, target_chars: int = 420, max_chars: int = 700) -> list[Segment]:
    blocks = analyze_text(text).blocks
    cfg = SegmentationConfig(
        target_chars=target_chars, min_chars=120, max_chars=max_chars,
        close_slack=0.45, hard_start_min_chars=200,
        respect_paragraph_boundary=True)
    return segment_text(blocks, lambda b: b.text, cfg)


def _pauses(text: str, language: str = "German", max_chars: int = 700):
    segs = _segs(text, max_chars=max_chars)
    assign_pauses(segs, style="relaxed", speed=1.0, strategy="narrative",
                  language=language)
    return segs


def test_german_sentence_pause_respected():
    text = "Die Mathematik ist die Sprache der Zahlen."
    segs = _pauses(text, "German")
    assert segs[-1].pause_after_s >= 0.50, \
        f"final sentence pause too small: {segs[-1].pause_after_s}"


def test_english_relaxed_pauses_on_oversize():
    # Sehr langer englischer Satz (>700 Zeichen), damit die Segmentierung
    # auf Klausel-/Komma-Grenzen aufteilt und die narrative-Pause
    # zwischen den Segmenten Atemraum erzeugt.
    text = ("The mathematics, the physics, the chemistry, and the biology "
            "of the natural world, along with the quiet practice of "
            "careful observation, the discipline of systematic "
            "experimentation, the slow accumulation of evidence, and "
            "the patient work of generations of inquirers, thinkers, "
            "writers, and teachers — these disciplines, these practices, "
            "and these quiet habits of mind form the foundation upon "
            "which modern science, in all its beauty, in all its rigor, "
            "and in all its quiet wonder, has been built over centuries "
            "of inquiry, doubt, debate, correction, and the slow "
            "careful labor of people who simply wanted to understand "
            "the world a little better than they found it.")
    segs = _pauses(text, "English", max_chars=420)
    assert len(segs) >= 2, f"expected multiple segments, got {len(segs)}"
    pauses = [s.pause_after_s for s in segs]
    assert min(pauses) >= 0.20, f"min pause too small: {min(pauses)}"
    assert pauses[-1] >= 0.45, f"final pause too small: {pauses[-1]}"


def test_paragraph_pause_larger_than_sentence():
    text = ("Der erste Gedanke ist kurz.\n\n"
            "Der zweite Absatz bringt mehr Ruhe in die Rede.")
    segs = _pauses(text, "German")
    types = [s.pause_type for s in segs]
    assert "paragraph" in types, f"expected paragraph pause, got {types}"
    para_pause = max(s.pause_after_s for s in segs if s.pause_type == "paragraph")
    assert para_pause >= 1.0, f"paragraph pause too small: {para_pause}"


def test_default_preset_is_narrative_relaxed():
    from app.prosody.presets import get_preset
    for name in ("deep_documentary", "en_documentary", "de_documentary"):
        p = get_preset(name)
        assert p["pause_strategy"] == "narrative", \
            f"{name}: expected narrative, got {p['pause_strategy']}"
        assert p["pause_style"] == "relaxed", \
            f"{name}: expected relaxed, got {p['pause_style']}"


def test_pause_level_ordering():
    from app.prosody.german import PAUSE_STRATEGIES
    nar = PAUSE_STRATEGIES["narrative"]
    assert 0.20 <= nar["after_comma"] <= 0.45
    assert 0.45 <= nar["after_semicolon"] <= 0.75
    assert 0.45 <= nar["after_colon"] <= 0.80
    assert nar["paragraph"] >= 0.90
    assert nar["chapter"] >= 1.5


def test_english_pause_level_ordering():
    from app.prosody.english import PAUSE_STRATEGIES_EN
    nar = PAUSE_STRATEGIES_EN["narrative"]
    assert 0.18 <= nar["after_comma"] <= 0.40
    assert 0.40 <= nar["after_semicolon"] <= 0.75
    assert 0.40 <= nar["after_colon"] <= 0.80
    assert nar["paragraph"] >= 0.90
    assert nar["chapter"] >= 1.5


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name}: {e}")
            except Exception as e:
                fails += 1
                import traceback
                print(f"ERROR {name}: {e}")
                traceback.print_exc()
    sys.exit(1 if fails else 0)
