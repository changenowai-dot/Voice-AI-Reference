"""Unit-Tests: Zahlen, Normalisierung, Analyse, Sprachprüfung (E, G, P)."""
from __future__ import annotations


def test_numbers_de():
    from app.text.numbers import (num_to_words_de, ordinal_de,
                                  year_to_words_de)
    assert num_to_words_de(0) == "null"
    assert num_to_words_de(7) == "sieben"
    assert num_to_words_de(21) == "einundzwanzig"
    assert num_to_words_de(101) == "einhunderteins"
    assert num_to_words_de(1999) == "eintausendneunhundertneunundneunzig"
    assert num_to_words_de(1024) == "eintausendvierundzwanzig"
    assert num_to_words_de(1_000_000) == "eine Million"
    assert year_to_words_de(1999) == "neunzehnhundertneunundneunzig"
    assert year_to_words_de(2024) == "zweitausendvierundzwanzig"
    assert ordinal_de(1) == "erste" and ordinal_de(3) == "dritte"
    assert ordinal_de(25) == "fünfundzwanzigste"
    assert ordinal_de(47) == "siebenundvierzigste"
    assert ordinal_de(30) == "dreißigste"


def test_numbers_en():
    from app.text.numbers import num_to_words_en, ordinal_en, year_to_words_en
    assert num_to_words_en(21) == "twenty-one"
    assert num_to_words_en(1999) == "one thousand nine hundred ninety-nine"
    assert year_to_words_en(1999) == "nineteen ninety-nine"
    assert year_to_words_en(2024) == "twenty twenty-four"
    assert ordinal_en(1) == "first" and ordinal_en(21) == "twenty-first"


def test_normalize_de_cases():
    from app.text.normalize import NormalizationReport, normalize_text
    rep = NormalizationReport()
    out = normalize_text("1999, 25.12.2024, 14:30 Uhr, 3,50 €, 97 %, 8 GB, "
                          "1.024.576, -12,5 °C, z.B. etc., Dr. Müller, CPU",
                          "German", rep)
    assert "neunzehnhundertneunundneunzig" in out
    assert "fünfundzwanzigste Dezember zweitausendvierundzwanzig" in out
    assert "vierzehn Uhr dreißig" in out
    assert "drei Euro und fünfzig" in out
    assert "siebenundneunzig Prozent" in out
    assert "acht Gigabyte" in out
    assert "eine Million vierundzwanzigtausendfünfhundertsechsundsiebzig" in out
    assert "minus zwölf Komma fünf Grad Celsius" in out
    assert "zum Beispiel" in out and "et cetera" in out
    assert "Doktor" in out and "C P U" in out
    assert "€" not in out and "%" not in out


def test_normalize_en_cases():
    from app.text.normalize import normalize_text
    out = normalize_text("In 2024, $3.50, 97%, 8 GB, 1,024,576 users, "
                          "e.g. Dr. Smith met the FBI.", "English")
    assert "twenty twenty-four" in out
    assert "three dollars and fifty" in out
    assert "ninety-seven percent" in out
    assert "eight gigabytes" in out
    assert "one million twenty-four thousand five hundred seventy-six" in out
    assert "for example" in out and "F B I" in out


def test_normalize_urls_emails():
    from app.text.normalize import normalize_text
    out = normalize_text("Siehe https://www.example.com/x?y=1 und "
                          "max.mustermann@example.org!", "German")
    assert "example Punkt com" in out
    assert "mustermann ät example" in out
    assert "http" not in out


def test_normalize_preserves_content():
    """Inhalt darf nicht verändert werden – nur die gesprochene Form."""
    from app.text.normalize import normalize_text
    src = "Die Geschwindigkeit beträgt 299.792,458 km pro Sekunde."
    out = normalize_text(src, "German")
    assert "Geschwindigkeit" in out and "Sekunde" in out
    assert "299" not in out           # Zahl wurde gesprochen
    assert "792" not in out


def test_sentences_split():
    from app.text.analyze import split_sentences
    s = split_sentences("Dr. Müller kam um 8:30 Uhr. Er aß 3,5 Brötchen. "
                        "Warum? Weil er es konnte!")
    assert len(s) == 4
    s2 = split_sentences("Am 1. Mai ging er. Kapitel IV folgte.")
    assert len(s2) == 2


def test_analysis_structure():
    from app.text.analyze import analyze_text
    txt = ("# Kapitel eins\n\nErster Absatz mit Satz. Noch einer.\n\n"
           "- Punkt eins\n- Punkt zwei\n\n"
           "„Ein Zitat bleibt.\"\n\nZweiter Absatz. 1999 war wichtig.")
    res = analyze_text(txt, "German")
    assert res.stats.headings >= 1
    assert res.stats.list_items == 2
    assert res.stats.paragraphs >= 2
    assert res.stats.years == 1
    assert res.stats.sentences >= 4


def test_langdetect():
    from app.text.langdetect import check_language_plausibility
    de = ("Der Mensch ist ein Seil, gespannt zwischen Tier und Übermensch. "
          "Wir haben die Kunst, damit wir nicht an der Wahrheit zugrunde gehen.")
    en = ("The quick brown fox jumps over the lazy dog. "
          "This is a test of the emergency broadcasting system today.")
    assert check_language_plausibility(de, "German").plausible
    assert check_language_plausibility(en, "English").plausible
    warn = check_language_plausibility(en, "German")
    assert not warn.plausible and warn.warning   # Widerspruch -> nur Warnung


def test_roman_numerals():
    from app.text.normalize import normalize_text
    out = normalize_text("Kapitel IV und Kapitel XIX", "German")
    assert "Kapitel vier" in out and "Kapitel neunzehn" in out
