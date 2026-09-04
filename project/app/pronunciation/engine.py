"""Aussprache-Engine (Anforderung 12 + 14, Phase 1 erweitert).

Pipeline-Priorität (Anforderung 8):
1. Benutzer-Aussprachewörterbuch (inkl. exakter Schreibweisen/Alternativen)
2. explizite deutsche Regeln: Fremdwort-/Anglizismus-Entscheidung
3. erkannte Eigennamen (Gazetteer + Heuristik, Kennzeichnung statt Raten)
4. Qwen-Standardverhalten (Normalisierung läuft separat davor)

Liefert zusätzlich Metadaten für den GermanNaturalnessScore:
Namen-Abdeckung, Fremdwort-Entscheidungen, gekennzeichnete Stellen.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .dictionary import PronunciationDictionary
from .foreign_words import analyze_foreign_words, apply_loanwords
from .names import NameMention, scan_names
from .tech_terms import (apply_tech_germanization,
                         find_uncovered_tech_terms, german_tech_map)


@dataclass
class PronunciationResult:
    text: str
    replacements: list = field(default_factory=list)
    unknown_problem_words: list = field(default_factory=list)
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
        # 2b) Fachwort-Germanisierung (Phase 3 §20) – vor dem Wörterbuch,
        #     damit Benutzer-Einträge die finale Ersetzung dominieren
        tech_repls: list = []
        if self.tech_germanization and language.lower().startswith("ger"):
            text, tech_repls = apply_tech_germanization(
                text, language, skip=set(self.dictionary.user_entries()))

        # 2) explizite Fremdwort-/Anglizismusregeln (vor dem Wörterbuch,
        #    damit Benutzer-Einträge die finale Ersetzung dominieren)
        text, loanword_repls = apply_loanwords(text, language)

        # 1) Wörterbuch (Benutzer > Fachwort-Layer > Built-ins)
        text, repls = self.dictionary.apply_to_text(text, language)
        pre = tech_repls + loanword_repls
        repls = pre + [
            r for r in repls if r["from"].lower() not in
            {lr["from"].lower() for lr in pre}]

        result = PronunciationResult(text=text, replacements=repls)

        if suggest_unknown or collect_meta:
            # 3) Eigennamen scannen (mit aktueller Ersetzungsliste)
            names = scan_names(text, self.dictionary.active_terms(language))
            result.name_mentions = names
            result.coverage = self.dictionary.coverage_for(names, language)
            result.risky_uncovered_names = [
                n for n in names if n.risk and not n.covered]
            result.foreign_decisions = analyze_foreign_words(text, language)
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
        return result
