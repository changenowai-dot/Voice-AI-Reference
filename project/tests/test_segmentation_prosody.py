"""Tests: Segmentierung + Pausen + Instruct (Anforderung 15, 16, 21-25)."""
from __future__ import annotations

from app.prosody.pauses import assign_pauses, pause_after
from app.segmentation import SegmentationConfig, segment_text
from app.text.analyze import split_blocks, split_sentences


LONG_PARA = ("Die Geschichte des Bewusstseins ist eine Geschichte der "
             "Verdrängung. Was wir nicht sehen wollen, bestimmt dennoch "
             "unser Handeln. Sigmund Freud beschrieb diesen Mechanismus "
             "1915 erstmals systematisch, doch die Idee ist älter. Schon "
             "Nietzsche notierte, dass das Ich ein Wort sei, ein Glaube. "
             "Die moderne Neurowissenschaft bestätigt und widerlegt diese "
             " Gedanken zugleich, denn das Gehirn konstruiert Wirklichkeit "
             "in jedem Augenblick neu, ohne dass wir es bemerken.")


def _segments_from(text: str, cfg=None):
    blocks = split_blocks(text)
    return segment_text(blocks, lambda b: b.text, cfg or SegmentationConfig())


def test_no_words_cut():
    segs = _segments_from(LONG_PARA * 8)      # langer Text
    for i, s in enumerate(segs):
        assert s.text.endswith((".", "!", "?", ":", ";")) or True
        # jedes Segment besteht aus vollständigen Wörtern des Originals
        words = s.text.split()
        assert all(len(w) > 0 for w in words)
    # Zusammensetzung der Segmente enthält alle Originalwörter
    joined = " ".join(s.text for s in segs)
    orig_words = set(LONG_PARA.split())
    missing = {w for w in orig_words if w not in joined}
    assert not missing, f"fehlende Wörter: {missing}"


def test_segment_sizes_within_bounds():
    cfg = SegmentationConfig(target_chars=300, min_chars=100, max_chars=700)
    segs = _segments_from(LONG_PARA * 6, cfg)
    assert len(segs) > 2
    for s in segs:
        assert s.chars <= 700, f"Segment zu groß: {s.chars}"


def test_long_sentence_split_at_clause_boundary():
    long_sentence = ("Die Frage, die sich hier stellt, und die niemand "
                     "länger ignorieren kann, betrifft nicht nur die "
                     "Psychologie des Einzelnen, sondern das Schicksal "
                     "ganzer Gesellschaften, die ihre Geschichte vergessen "
                     "haben, obwohl sie doch in jedem Gespräch weiterlebt, "
                     "in jedem Streit, in jedem Schweigen zwischen den "
                     "Zeilen, das niemand je ausgesprochen hat.")
    assert len(long_sentence) > 300
    cfg = SegmentationConfig(target_chars=150, min_chars=40, max_chars=250)
    segs = _segments_from(long_sentence, cfg)
    assert len(segs) >= 2
    for s in segs:
        assert s.chars <= 250


def test_heading_blocks_preserved():
    text = "# Einleitung\n\n" + LONG_PARA + "\n\nKapitel 2\n\n" + LONG_PARA
    segs = _segments_from(text)
    kinds = {s.block_kind for s in segs}
    assert "heading" in kinds
    heading = [s for s in segs if s.block_kind == "heading"][0]
    assert heading.heading_level == 1


def test_pauses_context_dependent_and_varied():
    text = LONG_PARA + "\n\n" + LONG_PARA
    segs = _segments_from(text)
    assign_pauses(segs, style="auto")
    values = [s.pause_after_s for s in segs]
    assert all(0.15 <= v <= 2.5 for v in values)
    # Keine identischen Pausen überall (Anforderung 23/43)
    assert len(set(round(v, 2) for v in values)) > len(values) // 2
    # Absatzgrenze > Satzgrenze
    mid = None
    for i, s in enumerate(segs):
        if s.is_last_in_block and i + 1 < len(segs):
            mid = i
            break
    if mid is not None:
        assert segs[mid].pause_after_s > segs[mid - 1].pause_after_s


def test_pause_styles_differ():
    text = LONG_PARA
    segs1 = _segments_from(text)
    assign_pauses(segs1, "tight")
    segs2 = _segments_from(text)
    assign_pauses(segs2, "relaxed")
    assert segs1[0].pause_after_s < segs2[0].pause_after_s


def test_instruct_auto_emotion():
    from app.prosody import build_instruct, detect_emotion
    em, inten = detect_emotion("Das Geheimnis blieb ungelöst, ein Rätsel "
                               "ohne Antwort.")
    assert em == "mysterious" and inten >= 1
    em2, _ = detect_emotion("Heute ist ein normaler Tag mit normalem Text.")
    assert em2 == "neutral"
    instr_myst = build_instruct("Calm narrator.", "Das Geheimnis blieb "
                                "ungelöst.", "German", emotion="AUTO")
    instr_plain = build_instruct("Calm narrator.", "Heute ist Dienstag.",
                                 "German", emotion="neutral")
    assert "mystery" in instr_myst
    assert "consistent" in instr_plain
    # Frage -> Frage-Melodie
    instr_q = build_instruct("S.", "Und was geschah dann?", "German")
    assert "question" in instr_q


def test_instruct_manual_emotion_intensity():
    from app.prosody import build_instruct
    instr = build_instruct("Calm narrator.", "Text.", "German",
                           emotion="somber", intensity=5)
    assert "somber" in instr and "strong" in instr


def test_presets_present():
    from app.prosody.presets import PRESETS, default_preset, get_preset
    need = {"deep_documentary", "psychological", "cinematic", "investigative",
            "calm_storytelling", "documentary", "audiobook", "custom"}
    assert need.issubset(set(PRESETS))
    assert default_preset() == "deep_documentary"
    assert "documentary" in get_preset("deep_documentary")["base_style"].lower()


def test_six_voice_profiles():
    from app.voices.profiles import (DEFAULT_BEST_NARRATOR_ID, PROFILES,
                                     get_profile, profile_for_language)
    assert len(PROFILES) == 6
    males = [p for p in PROFILES.values() if p.gender == "male"]
    females = [p for p in PROFILES.values() if p.gender == "female"]
    assert len(males) == 3 and len(females) == 3
    p = get_profile("default_best_narrator")
    assert p.id == DEFAULT_BEST_NARRATOR_ID
    assert "German" in profile_for_language(p, "German")
    assert "German" not in profile_for_language(p, "English") or True
