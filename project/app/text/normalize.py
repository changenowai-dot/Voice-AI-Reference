"""Textnormalisierung für TTS (Anforderung 11).

Wandelt Zahlen, Jahreszahlen, Datumsangaben, Uhrzeiten, Prozentangaben,
Währungen, Abkürzungen, Akronyme, Sonderzeichen, Klammern, Gedankenstriche,
URLs und E-Mail-Adressen in saubere Sprechtexte um – getrennt für Deutsch
und Englisch. Der Originaltext bleibt unangetastet; nur die TTS-Version
wird normalisiert (Original und TTS-Version bleiben intern getrennt).

Die Normalisierung verändert bewusst nur die *gesprochene* Repräsentation,
nie den Inhalt.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .numbers import (num_to_words_de, num_to_words_en, ordinal_de,
                      ordinal_en, roman_to_int, year_to_words_de,
                      year_to_words_en)

# --------------------------------------------------------------------------- 
# Abkürzungs- und Akronym-Tabellen
# ---------------------------------------------------------------------------
ABBR_DE = {
    "z.B.": "zum Beispiel", "z. B.": "zum Beispiel", "z.B": "zum Beispiel",
    "bspw.": "beispielsweise", "bzw.": "beziehungsweise",
    "etc.": "et cetera", "evtl.": "eventuell", "ggf.": "gegebenenfalls",
    "u.a.": "unter anderem", "u. a.": "unter anderem",
    "u.s.w.": "und so weiter", "usw.": "und so weiter",
    "v.a.": "vor allem", "v. a.": "vor allem",
    "v.Chr.": "vor Christus", "v. Chr.": "vor Christus",
    "n.Chr.": "nach Christus", "n. Chr.": "nach Christus",
    "Jh.": "Jahrhundert", "Jhd.": "Jahrhundert",
    "ca.": "circa", "inkl.": "inklusive", "exkl.": "exklusive",
    "Std.": "Stunden", "Min.": "Minuten", "Sek.": "Sekunden",
    "i.d.R.": "in der Regel", "i. d. R.": "in der Regel",
    "u.U.": "unter Umständen", "u. U.": "unter Umständen",
    "z.T.": "zum Teil", "z. T.": "zum Teil", "v.H.": "von Hundert",
    "h.M.": "herrschender Meinung", "a.a.O.": "am angegebenen Ort",
    "Dr.": "Doktor", "Prof.": "Professor", "St.": "Sankt",
    "Nr.": "Nummer", "Tel.": "Telefon", "bsp.": "beispielsweise",
    "d.h.": "das heißt", "d. h.": "das heißt",
    "a.D.": "außer Dienst", "ff.": "folgende", "Abs.": "Absatz",
    "Art.": "Artikel", "Gl.": "Gleichung", "vgl.": "vergleiche",
    "Jahrhunderte": "Jahrhunderte", "rd.": "rund", "sog.": "sogenannt",
}
ABBR_EN = {
    "e.g.": "for example", "i.e.": "that is", "etc.": "et cetera",
    "etc": "et cetera", "vs.": "versus", "vs": "versus",
    "Dr.": "Doctor", "Prof.": "Professor", "Mr.": "Mister",
    "Mrs.": "Missus", "Ms.": "Miss", "St.": "Saint",
    "approx.": "approximately", "cf.": "compare", "A.D.": "A D",
    "B.C.": "B C", "No.": "Number", "Vol.": "Volume",
    "fig.": "figure", "min.": "minutes", "max.": "maximum",
}

# Aussprechbare Akronyme (als Wort gesprochen) – alles andere wird buchiert
PRONOUNCEABLE_ACRONYMS = {
    "NASA", "UNO", "UNESCO", "NATO", "CERN", "WHO", "GAFAM", "OTAN",
    "BÖRSE", "AIDS", "COVID", "LASER", "RADAR", "SIM", "PIN", "RAM",
    "ROM", "AI", "WI-FI", "WLAN", "DAX", "TELEKOM",
}
# Fest definierte Buchier-Akronyme
SPELL_OUT = {
    "USA", "USSR", "NSA", "FBI", "CIA", "KGB", "GPU", "CPU", "TPU", "NPU",
    "API", "USB", "SSD", "HDD", "LED", "OLED", "LCD", "URL", "HTTP", "HTTPS",
    "DNA", "RNA", "ADHS", "PTBS", "LKW", "PKW", "AG", "GMBH", "EG",
    "EC", "EDV", "SPD", "CDU", "CSU", "FDP", "IQ", "EQ", "LLM", "GPT",
    "TTS", "STT", "CEO", "CFO", "CTO", "PPP", "BIP", "HNO", "DJ",
}

# Einheiten (mit Zahlen)
UNITS_DE = {
    "km": "Kilometer", "kg": "Kilogramm", "g": "Gramm", "mg": "Milligramm",
    "t": "Tonnen", "ml": "Milliliter", "l": "Liter", "cm": "Zentimeter",
    "m": "Meter", "mm": "Millimeter", "km/h": "Kilometer pro Stunde",
    "GB": "Gigabyte", "MB": "Megabyte", "KB": "Kilobyte", "TB": "Terabyte",
    "kWh": "Kilowattstunden", "kW": "Kilowatt", "W": "Watt",
    "Hz": "Hertz", "kHz": "Kilohertz", "MHz": "Megahertz",
    "GHz": "Gigahertz", "ps": "Pikosekunden", "ns": "Nanosekunden",
    "ms": "Millisekunden", "min": "Minuten", "h": "Stunden", "s": "Sekunden",
    "Jahre": "Jahre", "€": "Euro", "%": "Prozent", "°C": "Grad Celsius",
    "°F": "Grad Fahrenheit", "°": "Grad",
}
UNITS_EN = {
    "km": "kilometers", "kg": "kilograms", "g": "grams", "mg": "milligrams",
    "ml": "milliliters", "l": "liters", "cm": "centimeters", "m": "meters",
    "mm": "millimeters", "km/h": "kilometers per hour",
    "GB": "gigabytes", "MB": "megabytes", "KB": "kilobytes", "TB": "terabytes",
    "kWh": "kilowatt hours", "kW": "kilowatts", "W": "watts",
    "Hz": "hertz", "kHz": "kilohertz", "MHz": "megahertz",
    "GHz": "gigahertz", "ms": "milliseconds", "min": "minutes",
    "h": "hours", "s": "seconds", "%": "percent", "€": "euros",
    "°C": "degrees Celsius", "°F": "degrees Fahrenheit", "°": "degrees",
}

MONTHS_DE = {
    "01": "Januar", "02": "Februar", "03": "März", "04": "April",
    "05": "Mai", "06": "Juni", "07": "Juli", "08": "August",
    "09": "September", "10": "Oktober", "11": "November", "12": "Dezember",
    "1": "Januar", "2": "Februar", "3": "März", "4": "April", "5": "Mai",
    "6": "Juni", "7": "Juli", "8": "August", "9": "September",
    "10": "Oktober", "11": "November", "12": "Dezember",
}
MONTHS_EN = {
    "01": "January", "02": "February", "03": "March", "04": "April",
    "05": "May", "06": "June", "07": "July", "08": "August",
    "09": "September", "10": "October", "11": "November", "12": "December",
    "1": "January", "2": "February", "3": "March", "4": "April",
    "5": "May", "6": "June", "7": "July", "8": "August", "9": "September",
    "10": "October", "11": "November", "12": "December",
}

_NUM = r"\d+"


@dataclass
class NormalizationReport:
    replacements: list = field(default_factory=list)   # (original, ersatz, regel)

    def add(self, original: str, replacement: str, rule: str) -> None:
        self.replacements.append({"from": original, "to": replacement,
                                  "rule": rule})

    @property
    def count(self) -> int:
        return len(self.replacements)


class _Sub:
    """Hilfs-Wrapper: Regex-Ersetzung mit Protokollierung."""

    def __init__(self, text: str, report: NormalizationReport, lang: str):
        self.text = text
        self.report = report
        self.lang = lang

    def sub(self, pattern: str, repl, rule: str, flags: int = 0) -> "_Sub":
        rx = re.compile(pattern, flags)

        def _r(m: re.Match) -> str:
            out = repl(m)
            if out is None:
                return m.group(0)
            out = str(out)
            if out != m.group(0):
                self.report.add(m.group(0), out, rule)
            return out

        self.text = rx.sub(_r, self.text)
        return self


def _spell_acronym(token: str, lang: str) -> str:
    """ABC -> A B C; NASA -> NASA (als Wort gesprochen)."""
    t = token.strip(".,;:!?")
    if not t.isupper() or len(t) < 2:
        return token
    if t in PRONOUNCEABLE_ACRONYMS:
        return token
    has_vowel = any(c in "AEIOUÄÖÜ" for c in t)
    if has_vowel and len(t) <= 5 and t not in SPELL_OUT:
        # Aussprechbar wirkende Kurzwörter unangetastet lassen (z. B. RAM, WLAN)
        return token
    return " ".join(t)


def _num_words(num_str: str, lang: str, standalone: bool = False) -> str:
    n = int(num_str)
    if lang == "de":
        return num_to_words_de(n, standalone)
    return num_to_words_en(n)


def _year_words(y: int, lang: str) -> str:
    return year_to_words_de(y) if lang == "de" else year_to_words_en(y)


def normalize_text(text: str, language: str,
                   report: NormalizationReport | None = None) -> str:
    """Normalisiert Text für TTS. language: 'German'|'English'."""
    lang = "de" if language.lower().startswith("ger") else "en"
    report = report or NormalizationReport()
    s = _Sub(text, report, lang)

    # --- 0) Unicode-Bereinigung (Sonderzeichen, Anführungszeichen, Striche)
    s.sub(r"[\u201C\u201D\u201E\u201F\u2033\u2036\u2018\u2019\u201B\u2032\"]",
          lambda m: "", "quotes")
    s.sub(r"[\u00AD\u200B\u200C\u200D\uFEFF]", lambda m: "", "invisible")
    s.sub(r"[\u2010\u2011\u2012\u2013\u2212\uFE63\uFF0D]", lambda m: "-",
          "hyphen")
    # Ellipse: Satzende -> Punkt, mittig -> Komma (dramatische Pause
    # setzt die Prosodie-Annotation darüber)
    s.sub(r"\u2026(?=\s|$|[.,;!?])", lambda m: ".", "ellipsis_end")
    s.sub(r"\u2026", lambda m: ",", "ellipsis_mid")
    s.sub(r"\.\.\.(?=\s|$|[.,;!?])", lambda m: ".", "ellipsis_end")
    s.sub(r"\.\.\.", lambda m: ",", "ellipsis_mid")
    s.sub(r"[\u2022\u25CF\u25AA\u25E6\u00B7\u2043]", lambda m: ", ", "bullet")
    s.sub(r"[\u2192\u21D2]", lambda m: (" zu " if lang == "de" else " to "),
          "arrow", flags=0)
    s.sub(r"[«»]", lambda m: "", "guillemets")
    s.sub(r"\u00D7", lambda m: " x ", "times")
    s.sub(r"\u2248", lambda m: (" etwa " if lang == "de" else " about "),
          "approx")

    # --- 0b) Paragraphenzeichen (§§ 12 -> Paragraph zwölf) --------------------
    s.sub(r"\u00A7\u00A7\s*(\d+)", lambda m: "Paragraph " + _num_words(m.group(1), lang), "para")
    s.sub(r"\u00A7\s*(\d+)", lambda m: "Paragraph " + _num_words(m.group(1), lang), "para")

    # --- 1) E-Mail-Adressen -------------------------------------------------
    s.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
          lambda m: m.group(0).replace("@", " ät " if lang == "de" else " at "
                      ).replace(".", " Punkt " if lang == "de" else " dot "),
          "email")

    # --- 2) URLs ------------------------------------------------------------
    def _url(m: re.Match) -> str:
        url = m.group(0)
        body = re.sub(r"^https?://", "", url)
        body = re.sub(r"^www\.", "", body)
        body = body.split("?")[0].split("#")[0].split("/")[0]
        body = body.rstrip(".,;:!?")
        return body.replace(".", " Punkt " if lang == "de" else " dot ")
    s.sub(r"(?:https?://|www\.)[^\s,;!)\"'\]]+", _url, "url")

    # --- 3) Datumsangaben ---------------------------------------------------
    # 25.12.2024 / 25.12.24  -> de
    def _date_de(m: re.Match) -> str:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        if int(mo) > 12 or int(mo) < 1:
            return m.group(0)
        y_int = int(y)
        y_word = _year_words(y_int if y_int > 999 else 2000 + y_int, "de")
        return f"{ordinal_de(int(d))} {MONTHS_DE[mo]} {y_word}"
    if lang == "de":
        s.sub(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})\b(?!\d)", _date_de, "date")
        s.sub(r"\b(\d{1,2})\.(\d{1,2})\.(?!\d)",
              lambda m: (f"{ordinal_de(int(m.group(1)))} {MONTHS_DE[m.group(2)]}"
                         if 1 <= int(m.group(2)) <= 12 else m.group(0)),
              "date_short")
        # 12. Januar 2024
        s.sub(r"\b(\d{1,2})\.\s+(Januar|Februar|März|April|Mai|Juni|Juli|"
              r"August|September|Oktober|November|Dezember)\s+(\d{4})\b",
              lambda m: f"{ordinal_de(int(m.group(1)))} {m.group(2)} "
                        f"{_year_words(int(m.group(3)), 'de')}",
              "date_month_year")
        s.sub(r"\b(\d{1,2})\.\s+(Januar|Februar|März|April|Mai|Juni|Juli|"
              r"August|September|Oktober|November|Dezember)\b",
              lambda m: f"{ordinal_de(int(m.group(1)))} {m.group(2)}",
              "date_month")
        # ISO 2024-12-25
        s.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b",
              lambda m: f"{ordinal_de(int(m.group(3)))} {MONTHS_DE[m.group(2)]} "
                        f"{_year_words(int(m.group(1)), 'de')}",
              "date_iso")
    else:
        # December 25, 2024 / Dec 25 2024
        s.sub(r"\b(January|February|March|April|May|June|July|August|"
              r"September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b",
              lambda m: f"{m.group(1)} {ordinal_en(int(m.group(2)))}, "
                        f"{_year_words(int(m.group(3)), 'en')}",
              "date_month_year")
        s.sub(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
              lambda m: f"{ordinal_en(int(m.group(2)))} "
                        f"{MONTHS_EN[m.group(1)]} "
                        f"{_year_words(int(m.group(3)), 'en')}"
              if 1 <= int(m.group(1)) <= 12 else m.group(0),
              "date_us")
        s.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b",
              lambda m: f"{ordinal_en(int(m.group(3)))} {MONTHS_EN.get(m.group(2), m.group(2))} "
                        f"{_year_words(int(m.group(1)), 'en')}",
              "date_iso")

    # --- 4) Uhrzeiten -------------------------------------------------------
    def _time_de(m: re.Match) -> str:
        h, mi = int(m.group(1)), int(m.group(2))
        if mi == 0:
            return f"{num_to_words_de(h)} Uhr"
        return f"{num_to_words_de(h)} Uhr {num_to_words_de(mi)}"
    def _time_en(m: re.Match) -> str:
        h, mi = int(m.group(1)), int(m.group(2))
        if mi == 0:
            return f"{num_to_words_en(h)} o'clock"
        return f"{num_to_words_en(h)} {num_to_words_en(mi)}"
    time_pat = r"\b(\d{1,2}):(\d{2})\b(?=\s*(?:Uhr|uhr|h|am|pm|AM|PM|hrs)|[.,;)\s]|$)"
    if lang == "de":
        s.sub(r"\b(\d{1,2}):(\d{2})\s*(?:Uhr|uhr)\b",
              lambda m: (f"{num_to_words_de(int(m.group(1)))} Uhr "
                         f"{num_to_words_de(int(m.group(2)))}"),
              "time")
        s.sub(time_pat, _time_de, "time")
    else:
        s.sub(r"\b(\d{1,2}):(\d{2})\s*(a\.m\.|p\.m\.|AM|PM)\b",
              lambda m: f"{_time_en(m)} {m.group(3).replace('.', '')}",
              "time")
        s.sub(time_pat, _time_en, "time")

    # --- 5) Währungen -------------------------------------------------------
    if lang == "de":
        s.sub(r"(\d+),(\d{2})\s*€",
              lambda m: (f"{num_to_words_de(int(m.group(1)))} Euro "
                         + (f"und {num_to_words_de(int(m.group(2)))}"
                            if m.group(2) != "00" else "")),
              "currency")
        s.sub(r"€\s*(\d+),(\d{2})",
              lambda m: (f"{num_to_words_de(int(m.group(1)))} Euro "
                         + (f"und {num_to_words_de(int(m.group(2)))}"
                            if m.group(2) != "00" else "")),
              "currency")
        s.sub(r"(\d+)\s*€", lambda m: num_to_words_de(int(m.group(1))) + " Euro",
              "currency")
        s.sub(r"\$\s*(\d+(?:[.,]\d+)?)\b|\b(\d+(?:[.,]\d+)?)\s*\$",
              lambda m: _money_word(m, "de", "Dollar"), "currency")
        s.sub(r"(\d+(?:[.,]\d+)?)\s*(?:USD|US\$)\b",
              lambda m: _money_word(m, "de", "Dollar"), "currency")
    else:
        s.sub(r"\$\s*(\d+(?:\.\d+)?)\b|\b(\d+(?:\.\d+)?)\s*\$",
              lambda m: _money_word(m, "en", "dollars"), "currency")
        s.sub(r"(\d+(?:\.\d+)?)\s*(?:USD|US\$)\b",
              lambda m: _money_word(m, "en", "dollars"), "currency")
        s.sub(r"(?:€|EUR)\s*(\d+(?:\.\d+)?)\b|\b(\d+(?:\.\d+)?)\s*(?:€|EUR)\b",
              lambda m: _money_word(m, "en", "euros"), "currency")
        s.sub(r"£\s*(\d+(?:\.\d+)?)\b",
              lambda m: _money_word(m, "en", "pounds"), "currency")

    # --- 5b) Mio./Mrd. mit korrektem Numerus (5 Mio. -> 5 Millionen) --------
    # Muss VOR Dezimalwandlung laufen (sonst ist die Ziffer schon Text).
    def _mio(m: re.Match) -> str:
        word = {"Mio": ("Million", "Millionen"),
                "Mrd": ("Milliarde", "Milliarden")}[m.group(2)]
        try:
            n = float(m.group(1).replace(".", "").replace(",", "."))
        except ValueError:
            n = 2.0
        if n == 1:
            return f"eine {word[0]}"
        return f"{m.group(1)} {word[1]}"
    if lang == "de":
        s.sub(r"(\d[\d.,]*)\s*(Mio|Mrd)\.(?=\s|\W|$)", _mio, "abbr_mio")

    # --- 6) Prozent ---------------------------------------------------------
    s.sub(r"(-?\d+(?:[.,]\d+)?)\s*%",
          lambda m: _signed(_decimal_num(m.group(1).lstrip("-"), lang),
                            m.group(1).startswith("-"), lang) +
                    (" Prozent" if lang == "de" else " percent"),
          "percent")

    # --- 7) Temperaturen / Grade -------------------------------------------
    s.sub(r"(-?\d+(?:[.,]\d+)?)\s*°\s*C\b",
          lambda m: _signed(_decimal_num(m.group(1).lstrip("-"), lang),
                            m.group(1).startswith("-"), lang) +
                    (" Grad Celsius" if lang == "de" else " degrees Celsius"),
          "temperature")
    s.sub(r"(-?\d+(?:[.,]\d+)?)\s*°\s*F\b",
          lambda m: _signed(_decimal_num(m.group(1).lstrip("-"), lang),
                            m.group(1).startswith("-"), lang) +
                    (" Grad Fahrenheit" if lang == "de" else " degrees Fahrenheit"),
          "temperature")

    # --- 8) Einheiten mit Zahlen -------------------------------------------
    units = UNITS_DE if lang == "de" else UNITS_EN
    unit_pat = "|".join(re.escape(u) for u in
                        sorted(units, key=len, reverse=True))
    s.sub(rf"(-?\d+(?:[.,]\d+)?)\s*({unit_pat})\b",
          lambda m: _signed(_decimal_num(m.group(1).lstrip("-"), lang),
                            m.group(1).startswith("-"), lang) +
                    f" {units[m.group(2)]}",
          "unit")

    # --- 9) Jahreszahlen (vor normalen Zahlen!) ----------------------------
    # Deutsch-Natürlichkeit (Phase 1): Jahres-Lesart („neunzehnhundert…“)
    # nur bei Jahres-Kontext (Jahr/Jahrhundert/v.Chr./Datum) ODER bei
    # modernen Jahren 19xx/20xx/21xx; reine Mengen wie „1500 Bücher“
    # werden ausgeschrieben („eintausendfünfhundert“).
    _YEAR_CUE_BEFORE = (r"(?:Jahr(?:e|es|en)?|Jahrhundert(?:e|es|en)?|"
                        r"Jahrtausend(?:e|es|en)?|seit|um|im|von|bis|vor|nach|"
                        r"Frühling|Sommer|Herbst|Winter)\s+$")
    _YEAR_CUE_AFTER = (r"^\s*(?:v\.?\s*Chr\.?|n\.?\s*Chr\.?|geb\.|gest\.|"
                       r"verstorben|\()")
    if lang == "de":
        def _year_de(m: re.Match, left: str, right: str):
            y = int(m.group(1))
            if not (1100 <= y <= 2199):
                return m.group(0)
            modern = 1900 <= y <= 2199
            cued = re.search(_YEAR_CUE_BEFORE, left) is not None or \
                   re.match(_YEAR_CUE_AFTER, right) is not None
            follows_noun = re.match(r"\s+[A-ZÄÖÜ]", right) is not None
            if modern or cued or not follows_noun:
                return _year_words(y, "de")
            # Menge vor Substantiv („1500 Bücher“) -> ausgeschrieben
            return m.group(0)
        textpos = s.text
        out_parts = []
        last = 0
        for m in re.finditer(r"\b(1[1-9]\d{2}|20\d{2}|21\d{2})\b(?!\s*(?:%|€|\$))",
                             textpos):
            left = textpos[max(0, m.start() - 28):m.start()]
            right = textpos[m.end():m.end() + 14]
            repl = _year_de(m, left, right)
            if repl != m.group(0):
                out_parts.append(textpos[last:m.start()])
                out_parts.append(repl)
                last = m.end()
                s.report.add(m.group(0), repl, "year")
        out_parts.append(textpos[last:])
        s.text = "".join(out_parts)
    else:
        def _year(m: re.Match):
            y = int(m.group(1))
            if 1000 <= y <= 2199:
                return _year_words(y, "en")
            return m.group(0)
        s.sub(r"\b(1[5-9]\d{2}|20\d{2}|21\d{2})\b(?!\s*(?:%|€|\$))", _year, "year")

    # --- 10) Tausendertrennung + Dezimalzahlen ------------------------------
    if lang == "de":
        _strip_thousands(s, r"(\d)\.(\d{3})(?=[.,\s]\d|\b)")
        s.sub(r"-?\b(\d+),(\d+)\b",
              lambda m: _signed(_decimal_word_de(m.group(1), m.group(2)),
                                m.group(0).startswith("-"), lang), "decimal")
    else:
        _strip_thousands(s, r"(\d),(\d{3})(?=[.,\s]\d|\b)")
        s.sub(r"-?\b(\d+)\.(\d+)\b",
              lambda m: _signed(_decimal_word_en(m.group(1), m.group(2)),
                                m.group(0).startswith("-"), lang), "decimal")

    # --- 11) Ordinalzahlen (Rest) -------------------------------------------
    if lang == "de":
        s.sub(r"\b(\d{1,2})\.(?=\s)", lambda m: ordinal_de(int(m.group(1))),
              "ordinal")
    else:
        s.sub(r"\b(\d{1,2})(st|nd|rd|th)\b",
              lambda m: ordinal_en(int(m.group(1))), "ordinal")

    # --- 12) Buchstaben-Ziffern-Kombis (A4, B2, 4K, 5G) ----------------------
    def _alnum(m: re.Match) -> str:
        letter, digit = m.group(1), m.group(2)
        d_word = _num_words(digit, lang)
        return f"{letter} {d_word}"
    s.sub(r"\b([A-Z])(\d{1,2})\b", _alnum, "letter_digit")

    # --- 13) Römische Zahlen (eigenständige Zeilen + Kapitel-Präfixe) ---------
    def _roman(m: re.Match):
        v = roman_to_int(m.group(1))
        if v is None:
            return m.group(0)
        return _num_words(str(v), lang)
    s.sub(r"(?m)^\s*(IX|IV|V?I{1,3}|X{1,3}(IX|IV|V?I{0,3}))\s*\.?\s*$", _roman,
          "roman")
    s.sub(r"\b(Kapitel|Chapter|Teil|Part|Abschnitt)\s+"
          r"(IX|IV|V?I{1,3}|X{1,3}(IX|IV|V?I{0,3})|XXX|XL|L|LX|LXX|LXXX|XC|C)\b",
          lambda m: f"{m.group(1)} {_num_words(str(roman_to_int(m.group(2))), lang)}",
          "roman_chapter")

    # --- 14) Abkürzungen ------------------------------------------------------
    abbr = ABBR_DE if lang == "de" else ABBR_EN
    for a in sorted(abbr, key=len, reverse=True):
        if a in s.text:
            s.sub(r"(?<![\wÄÖÜäöüß.])" + re.escape(a) + r"(?=\s|$|[.,;:!?)])",
                  lambda m, _r=abbr[a]: _r, "abbr")

    # Römische Ordinalzahlen bei Namen: Ludwig XIV. -> Ludwig der Vierzehnte
    if lang == "de":
        _ROM = "X{0,3}(IX|IV|V?I{0,3})|X{1,3}"
        s.sub(r"\b([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)?)\s+"
              r"(XXX|XL|L|LX|LXX|LXXX|XC|C|IX|IV|V|VI|VII|VIII|I|II|III|X|XI|XII|XIII|XIV|XV|XVI|XVII|XVIII|XIX|XX)\.",
              lambda m: f"{m.group(1)} der "
                        f"{ordinal_de(roman_to_int(m.group(2))).capitalize()}",
              "roman_ordinal_name")
    # Initialen: "J. R. R. Tolkien" -> "J R R Tolkien"
    s.sub(r"\b([A-ZÄÖÜ])\.\s*(?=[A-ZÄÖÜ]\.)", lambda m: m.group(1) + " ",
          "initials")
    s.sub(r"\b([A-ZÄÖÜ])\.(?=\s+[A-ZÄÖÜ][a-z])", lambda m: m.group(1) + " ",
          "initial")

    # --- 15) Akronyme buchieren ------------------------------------------------
    s.sub(r"\b[A-ZÄÖÜ]{2,6}\b(?![a-zäöü])",
          lambda m: _spell_acronym(m.group(0), lang), "acronym")

    # --- 16) Klammern & Restzeichen ---------------------------------------------
    s.sub(r"[()\[\]{}<>]", lambda m: " ", "brackets")
    s.sub(r"[#*_~`|@¶†‡]", lambda m: " ", "symbols")
    s.sub(r"=", lambda m: (" gleich " if lang == "de" else " equals "),
          "equals")
    s.sub(r"\+", lambda m: (" plus " if lang == "de" else " plus "), "plus")
    s.sub(r"&", lambda m: (" und " if lang == "de" else " and "), "amp")
    s.sub(r"/(?=\s)", lambda m: (" oder " if lang == "de" else " or "),
          "slash")

    # --- 17) Einzelne übrig gebliebene Ganzzahlen --------------------------------
    s.sub(r"\b\d{1,15}\b",
          lambda m: _num_words(m.group(0), lang, standalone=True), "number")

    # --- 18) Aufräumen ------------------------------------------------------------
    s.sub(r"[ \t]{2,}", lambda m: " ", "space")
    s.sub(r"\s+([,.;:!?])", lambda m: m.group(1), "space_punct")
    s.sub(r" ([,.;:!?])", lambda m: m.group(1), "space_punct2")
    s.sub(r"(\w)--(\w)", lambda m: m.group(1) + ", " + m.group(2), "dash")
    # „ – “ / „ - “ als Parenthese/Gedankenpausen -> Komma
    s.sub(r"\s+[-–]\s+", lambda m: ", ", "dash_parenthetical")
    text_out = s.text.strip()
    text_out = re.sub(r"\n{3,}", "\n\n", text_out)
    return text_out


# ---------------------------------------------------------------- Helpers ---
def _signed(word: str, negative: bool, lang: str) -> str:
    if not negative:
        return word
    return "minus " + word


def _strip_thousands(s: "_Sub", pattern: str) -> None:
    """Entfernt Tausender-Trennzeichen iterativ (1.024.576 -> 1024576)."""
    prev = None
    while prev != s.text:
        prev = s.text
        s.sub(pattern, lambda m: m.group(1) + m.group(2), "thousands_sep")


def _decimal_num(raw: str, lang: str) -> str:
    raw = raw.replace(".", "," if lang == "de" else ".").replace(
        ",", "," if lang == "de" else ".")
    ip, _, fp = raw.partition("," if lang == "de" else ".")
    if not fp:
        return _num_words(ip, lang) if ip else "null"
    return _decimal_word(ip, fp, lang)


def _decimal_word(ip: str, fp: str, lang: str) -> str:
    if lang == "de":
        return f"{num_to_words_de(int(ip))} Komma " + " ".join(
            num_to_words_de(int(d), True) for d in fp)
    return f"{num_to_words_en(int(ip))} point " + " ".join(
        num_to_words_en(int(d)) for d in fp)


def _decimal_word_de(ip: str, fp: str) -> str:
    return _decimal_word(ip, fp, "de")


def _decimal_word_en(ip: str, fp: str) -> str:
    return _decimal_word(ip, fp, "en")


def _money_word(m: re.Match, lang: str, currency: str) -> str:
    raw = m.group(1) or m.group(2)
    sep = "," if lang == "de" else "."
    ip, _, fp = raw.partition(sep)
    words = _num_words(ip, lang)
    if lang == "de":
        if fp and fp != "00":
            if len(fp) == 2:
                return f"{words} {currency} und {_num_words(fp, lang)}"
            return f"{words} {currency} und " + " ".join(
                num_to_words_de(int(d), True) for d in fp)
        return f"{words} {currency}"
    if fp and fp != "00":
        return f"{words} {currency} and {_num_words(fp, lang)}"
    return f"{words} {currency}"
