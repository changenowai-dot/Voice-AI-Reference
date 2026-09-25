"""Aussprache-Engine (Anforderung 12 + 14, Phase 1 erweitert).

Pipeline-Priorität (Anforderung 8):
1. Benutzer-Aussprachewörterbuch (inkl. exakter Schreibweisen/Alternativen)
2. explizite deutsche Regeln: Fremdwort-/Anglizismus-Entscheidung
3. erkannte Eigennamen (Gazetteer + Heuristik, Kennzeichnung statt Raten)
4. Qwen-Standardverhalten (Normalisierung läuft separat davor)

Liefert zusätzlich Metadaten für den GermanNaturalnessScore:
Namen-Abdeckung, Fremdwort-Entscheidungen, gekennzeichnete Stellen.

Diagnostik-Logging (PRONUNCIATION_PREPROCESS_*):
Jeder Lauf schreibt strukturierte Log-Zeilen, damit im GUI-Produktionslauf
nachvollziehbar ist, ob die Aussprache-Optimierung angewendet wurde,
welche Begriffe erkannt und welche Ersetzungen vorgenommen wurden.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..logging_setup import get_logger, text_fingerprint as _fingerprint
from .dictionary import PronunciationDictionary
from .foreign_words import analyze_foreign_words, apply_loanwords
from .names import NameMention, scan_names
from .tech_terms import (apply_tech_germanization,
                         find_uncovered_tech_terms, german_tech_map)

log = get_logger("pronunciation.engine")

# Regel-ID-Präfixe – jede Schicht bekommt einen eindeutigen Namensraum,
# damit Audits/Regressionstests nachvollziehbar bleiben:
#   DE_TECH_<nr>   Fachwort-Germanisierung in tech_terms.py
#   DE_LOAN_<nr>   Fremdwort-/Anglizismus-Ersetzung in foreign_words.py
#   DE_DICT_<nr>   Wörterbuch-Eintrag (built-in oder user)
#   DE_NORM_<nr>   Textnormalisierung (Zahlen/Abkürzungen/Symbole)
#   DE_SUFFIX_*    generische Komposita-Suffixregel


@dataclass
class PronunciationResult:
    text: str
    replacements: list = field(default_factory=list)
    unknown_problem_words: list = field(default_factory=list)
    # Anzahl Woerter mit ä/ö/ü/ß im FINALEN TTS-Text (Observability,
    # UMLAUT-FIX 2026-09-24): beweist im Log, dass deutsche Sonderzeichen
    # den Preprocess codepoint-erhalten durchlaufen haben. Die Schicht
    # AENDERT keinen Text - sie macht die Umlaut-Kette pruefbar und
    # bricht bei kuenftigen Encoding-Regressionen sichtbar (Count 0).
    umlaut_words: int = 0
    # Phase-1-Metadaten
    name_mentions: list = field(default_factory=list)      # NameMention
    risky_uncovered_names: list = field(default_factory=list)
    foreign_decisions: list = field(default_factory=list)
    coverage: dict = field(default_factory=dict)

    @property
    def flagged_spots(self) -> list[str]:
        """Intern gekennzeichnete Problemstellen (Anforderung 10)."""
        spots = [f"{m.name} ({m.category}, Aussprache unsicher)"
                 for m in self.risky_uncovered_names]
        spots += [f"{d.word} (Fremdwort: {d.action})"
                  for d in self.foreign_decisions
                  if d.action == "leave"]
        return spots


class PronunciationEngine:
    def __init__(self, dictionary: PronunciationDictionary | None = None,
                 tech_germanization: bool = True):
        self.dictionary = dictionary or PronunciationDictionary()
        self.tech_germanization = tech_germanization
        if tech_germanization:
            self.dictionary.set_tech_layer(german_tech_map())

    def process(self, text: str, language: str,
                suggest_unknown: bool = True,
                collect_meta: bool = False) -> PronunciationResult:
        log.info("PRONUNCIATION_PREPROCESS_START language=%s chars=%d fp=%s",
                 language, len(text), _fingerprint(text))
        # 2b) Fachwort-Germanisierung (Phase 3 §20) – vor dem Wörterbuch,
        #     damit Benutzer-Einträge die finale Ersetzung dominieren
        tech_repls: list = []
        if self.tech_germanization and language.lower().startswith("ger"):
            text, tech_repls = apply_tech_germanization(
                text, language, skip=set(self.dictionary.user_entries()))
            for r in tech_repls:
                term = r.get("from", "")
                repl = r.get("to", "")
                rule = r.get("rule", "DE_TECH_term")
                log.info("PRONUNCIATION_TERM_DETECTED term=%r rule=%s",
                         term, rule)
                log.info(
                    "PRONUNCIATION_TERM_REPLACED original=%r tts=%r rule=%s",
                    term, repl, rule)

        # 2) explizite Fremdwort-/Anglizismusregeln (vor dem Wörterbuch,
        #    damit Benutzer-Einträge die finale Ersetzung dominieren)
        text, loanword_repls = apply_loanwords(text, language)
        for r in loanword_repls:
            rule = r.get("rule", "DE_LOAN_?")
            log.info("PRONUNCIATION_TERM_DETECTED term=%r rule=%s",
                     r.get("from"), rule)
            log.info(
                "PRONUNCIATION_TERM_REPLACED original=%r tts=%r rule=%s",
                r.get("from"), r.get("to"), rule)

        # 1) Wörterbuch (Benutzer > Fachwort-Layer > Built-ins)
        text, repls = self.dictionary.apply_to_text(text, language)
        for r in repls:
            rule = r.get("rule", "DE_DICT_entry")
            log.info("PRONUNCIATION_TERM_DETECTED term=%r rule=%s",
                     r.get("from"), rule)
            log.info(
                "PRONUNCIATION_TERM_REPLACED original=%r tts=%r rule=%s",
                r.get("from"), r.get("to"), rule)
        pre = tech_repls + loanword_repls
        repls = pre + [
            r for r in repls if r["from"].lower() not in
            {lr["from"].lower() for lr in pre}]

        result = PronunciationResult(text=text, replacements=repls)
        # UMLAUT-Observability (kein Texteingriff): Woerter mit ä/ö/ü/ß
        # im finalen TTS-Text zaehlen und im PREPROCESS_END-Log ausweisen.
        result.umlaut_words = sum(
            1 for w in re.findall(r"[A-Za-zÄÖÜäöüß]+", text)
            if re.search(r"[äöüßÄÖÜ]", w))

        if suggest_unknown or collect_meta:
            # 3) Eigennamen scannen (mit aktueller Ersetzungsliste)
            names = scan_names(text, self.dictionary.active_terms(language))
            result.name_mentions = names
            result.coverage = self.dictionary.coverage_for(names, language)
            result.risky_uncovered_names = [
                n for n in names if n.risk and not n.covered]
            result.foreign_decisions = analyze_foreign_words(text, language)
            for d in result.foreign_decisions:
                log.debug("PRONUNCIATION_TERM_DETECTED term=%r action=%s",
                          getattr(d, "word", None),
                          getattr(d, "action", None))
            if suggest_unknown:
                uncovered = find_uncovered_tech_terms(
                    text, language, self.dictionary.active_terms(language))
                result.unknown_problem_words = (
                    result.unknown_problem_words +
                    [{"term": t, "occurrences": 1, "type": "Fachwort",
                      "risk": True} for t in uncovered
                     if t not in {u["term"] for u in
                                  result.unknown_problem_words}])
            if suggest_unknown:
                name_terms = [
                    {"term": n.name, "occurrences": 1,
                     "type": n.category, "risk": n.risk}
                    for n in result.risky_uncovered_names]
                known = {u["term"] for u in result.unknown_problem_words}
                result.unknown_problem_words = (
                    name_terms +
                    [u for u in result.unknown_problem_words
                     if u["term"] not in {n["term"] for n in name_terms}
                     and u["term"] in known] +
                    [u for u in result.unknown_problem_words
                     if u["term"] not in known])
        log.info(
            "PRONUNCIATION_PREPROCESS_END replacements=%d "
            "unknown_problem_terms=%d chars_in=%d chars_out=%d "
            "umlaut_words=%d",
            len(repls), len(result.unknown_problem_words),
            len(text), len(result.text), result.umlaut_words)
        return result
