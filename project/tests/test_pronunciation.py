"""Tests: Aussprache-Wörterbuch + Engine (G, H)."""
from __future__ import annotations

from app.pronunciation import PronunciationDictionary, PronunciationEngine


def test_dictionary_crud():
    d = PronunciationDictionary()
    d.clear_all()
    d.add_entry("Xkcd", "iks-kom-si-di")
    assert "Xkcd" in d.user_entries()
    d.update_entry("Xkcd", "iks-kom-si-di-es")
    assert d.user_entries()["Xkcd"] == "iks-kom-si-di-es"
    assert d.delete_entry("Xkcd")
    assert "Xkcd" not in d.user_entries()
    assert not d.delete_entry("Xkcd")           # zweites Löschen: False


def test_dictionary_persistent():
    d1 = PronunciationDictionary()
    d1.clear_all()
    d1.add_entry("Beispielname", "Bei-spiel-na-me")
    d2 = PronunciationDictionary()              # frische Instanz, gleiche Datei
    assert "Beispielname" in d2.user_entries()
    d2.clear_all()


def test_builtin_overrides_and_priority():
    d = PronunciationDictionary()
    eng = PronunciationEngine(d)
    # Built-in vorhanden?
    text, repl = d.apply_to_text("NVIDIA und ChatGPT", "German")
    t_low = text.lower()
    assert "en-widia" in t_low and "tschät g p t" in t_low
    # Benutzer-Eintrag überschreibt Built-in
    d.add_entry("NVIDIA", {"de": "en-wi-di-a", "en": "en-vidia"})
    text2, _ = d.apply_to_text("NVIDIA", "German")
    assert "en-wi-di-a" in text2.lower()
    text3, _ = d.apply_to_text("NVIDIA", "English")
    assert "en-vidia" in text3.lower()


def test_apply_respects_word_boundaries():
    d = PronunciationDictionary()
    d.clear_all()
    d.add_entry("IDS", "ii-de-es")
    text, _ = d.apply_to_text("Die IDS-Kennung und IDSE nicht vergessen.", "German")
    assert "ii-de-es" in text.lower() or "ii-de es" in text.lower()
    assert "IDSE" in text                       # längerer Begriff unangetastet


def test_engine_suggests_unknown():
    d = PronunciationDictionary()
    d.clear_all()
    eng = PronunciationEngine(d)
    res = eng.process("Der Wissenschaftler Xzqarius untersuchte das Verhalten.",
                      "German")
    assert any(u["term"] == "Xzqarius"
               for u in res.unknown_problem_words)


def test_engine_process_applies():
    d = PronunciationDictionary()
    d.clear_all()
    d.add_entry("Göbekli Tepe", "Göbäkli Tepe")
    eng = PronunciationEngine(d)
    res = eng.process("Wir reisen nach Göbekli Tepe morgen.", "German")
    assert "Göbäkli Tepe".lower() in res.text.lower()
    assert len(res.replacements) == 1
