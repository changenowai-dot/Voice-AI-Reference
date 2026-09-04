"""Zahl-in-Wort-Konvertierung für Deutsch und Englisch.

Vollständige Implementation für 0 … 999.999.999.999 sowie Ordinalzahlen
(für Datumsangaben) und römische Zahlen.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------- Deutsch --
_DE_ONES = ["", "ein", "zwei", "drei", "vier", "fünf", "sechs", "sieben",
            "acht", "neun"]
_DE_ONES_FULL = ["", "eins", "zwei", "drei", "vier", "fünf", "sechs",
                 "sieben", "acht", "neun"]
_DE_TENS = ["", "", "zwanzig", "dreißig", "vierzig", "fünfzig", "sechzig",
            "siebzig", "achtzig", "neunzig"]
_DE_TEENS = {10: "zehn", 11: "elf", 12: "zwölf", 13: "dreizehn",
             14: "vierzehn", 15: "fünfzehn", 16: "sechzehn", 17: "siebzehn",
             18: "achtzehn", 19: "neunzehn"}
_DE_ORD = {1: "erste", 2: "zweite", 3: "dritte", 4: "vierte", 5: "fünfte",
           6: "sechste", 7: "siebte", 8: "achte", 9: "neunte"}


def _de_below_100(n: int, standalone: bool) -> str:
    if n < 10:
        return _DE_ONES_FULL[n] if standalone else _DE_ONES[n]
    if n < 20:
        return _DE_TEENS[n]
    ones, tens = n % 10, n // 10
    if ones == 0:
        return _DE_TENS[tens]
    return f"{_DE_ONES[ones]}und{_DE_TENS[tens]}"


def num_to_words_de(n: int, standalone: bool = True) -> str:
    if n == 0:
        return "null"
    if n < 0:
        return "minus " + num_to_words_de(-n, standalone)
    if n < 100:
        return _de_below_100(n, standalone)
    if n < 1_000:
        h, rest = divmod(n, 100)
        word = _DE_ONES[h] + "hundert"
        if rest:
            word += _de_below_100(rest, standalone)
        return word
    if n < 1_000_000:
        thousands, units = divmod(n, 1_000)
        t = "eintausend" if thousands == 1 else \
            num_to_words_de(thousands, False) + "tausend"
        if units:
            t += num_to_words_de(units, standalone)
        return t
    millions, rest = divmod(n, 1_000_000)
    if millions == 1:
        head = "eine Million"
    else:
        head = num_to_words_de(millions, False) + " Millionen"
    if rest:
        return head + " " + num_to_words_de(rest, standalone)
    return head


def _de_hundred_prefix(h: int) -> str:
    """11 -> 'elf', 19 -> 'neunzehn', 20 -> 'zwanzig' (für ...hundert-Jahre)."""
    if h < 10:
        return _DE_ONES[h]
    if h < 20:
        return _DE_TEENS[h]
    return _de_below_100(h, False)


def year_to_words_de(year: int) -> str:
    """1999 -> neunzehnhundertneunundneunzig; 2024 -> zweitausendvierundzwanzig."""
    if 1100 <= year <= 1999:
        h, rest = divmod(year, 100)
        base = _de_hundred_prefix(h) + "hundert"
        return base + (_de_below_100(rest, False) if rest else "")
    # 2000-2199: Zehner/Einer als vollständige Zahl („zweitausendeins“,
    # nicht „zweitausendein“) – natürliche deutsche Jahreslesart
    if 2000 <= year <= 2199:
        thousands, rest = divmod(year, 1000)
        base = "zweitausend"
        if rest:
            return base + num_to_words_de(rest, standalone=True)
        return base
    return num_to_words_de(year, standalone=True)


_DE_ORD_1_19 = {1: "erste", 2: "zweite", 3: "dritte", 4: "vierte",
                 5: "fünfte", 6: "sechste", 7: "siebte", 8: "achte",
                 9: "neunte", 10: "zehnte", 11: "elfte", 12: "zwölfte",
                 13: "dreizehnte", 14: "vierzehnte", 15: "fünfzehnte",
                 16: "sechzehnte", 17: "siebzehnte", 18: "achtzehnte",
                 19: "neunzehnte"}


def ordinal_de(n: int) -> str:
    if n <= 0:
        return str(n)
    if n <= 19:
        return _DE_ORD_1_19[n]
    # Ab 20 endet alles auf „ste“ – auch 23 (dreiundzwanzigste), 103 usw.
    return num_to_words_de(n, False) + "ste"


# --------------------------------------------------------------- Englisch --
_EN_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven",
            "eight", "nine", "ten", "eleven", "twelve", "thirteen",
            "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
            "nineteen"]
_EN_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
            "eighty", "ninety"]
_EN_SCALE = [(1_000_000_000, "billion"), (1_000_000, "million"), (1_000, "thousand")]
_EN_ORD_SPECIAL = {1: "first", 2: "second", 3: "third", 5: "fifth",
                   8: "eighth", 9: "ninth", 11: "eleventh", 12: "twelfth"}


def _en_below_100(n: int) -> str:
    if n < 20:
        return _EN_ONES[n]
    t, o = divmod(n, 10)
    return _EN_TENS[t] + ("-" + _EN_ONES[o] if o else "")


def num_to_words_en(n: int) -> str:
    if n < 0:
        return "minus " + num_to_words_en(-n)
    if n < 100:
        return _en_below_100(n)
    if n < 1_000:
        h, rest = divmod(n, 100)
        parts = [_EN_ONES[h], "hundred"]
        if rest:
            parts.append(_en_below_100(rest))
        return " ".join(parts)
    words: list[str] = []
    for value, name in _EN_SCALE:
        if n >= value:
            count, n = divmod(n, value)
            words.append(f"{num_to_words_en(count)} {name}")
    if n:
        words.append(num_to_words_en(n))
    return " ".join(words)


def year_to_words_en(year: int) -> str:
    if 1000 <= year <= 9999:
        h, rest = divmod(year, 100)
        head = num_to_words_en(h)          # nineteen, twenty, twenty-one …
        if rest == 0:
            return f"{head} hundred"
        if rest < 10:
            return f"{head} oh {_EN_ONES[rest]}"
        return f"{head} {_en_below_100(rest)}"
    return num_to_words_en(year)


def ordinal_en(n: int) -> str:
    if n in _EN_ORD_SPECIAL:
        return _EN_ORD_SPECIAL[n]
    if n < 20:
        return _EN_ONES[n] + "th"
    if n % 100 in (11, 12, 13):
        return num_to_words_en(n) + "th"
    if n % 10 == 0:
        base = num_to_words_en(n)
        return base[:-1] + "ieth" if base.endswith("y") else base + "th"
    base = num_to_words_en(n)
    tail = _EN_ORD_SPECIAL.get(n % 10, _EN_ONES[n % 10] + "th")
    return base.rsplit("-", 1)[0] + "-" + tail if "-" in base else base + tail


# ------------------------------------------------------------- Römisch -----
ROMAN_VALUES = [("M", 1000), ("CM", 900), ("D", 500), ("CD", 400),
                ("C", 100), ("XC", 90), ("L", 50), ("XL", 40), ("X", 10),
                ("IX", 9), ("V", 5), ("IV", 4), ("I", 1)]
_ROMAN_RE = re.compile(r"^M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")


def roman_to_int(s: str) -> int | None:
    s = s.strip().upper()
    if not s or not _ROMAN_RE.match(s):
        return None
    i, total = 0, 0
    for sym, val in ROMAN_VALUES:
        while s.startswith(sym, i):
            total += val
            i += len(sym)
    return total if 0 < total <= 3999 else None
