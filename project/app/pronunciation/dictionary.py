"""Dauerhafte Aussprache-Wörterliste (Anforderung 13).

Zwei Ebenen:
1. Built-in-Wörterbuch (mitgeliefert, read-only, app/pronunciation/builtins_*.json)
2. Benutzer-Wörterbuch (pronunciation/pronunciation.json) – dauerhaft,
   editierbar, einzeln löschbar, vollständig löschbar, unabhängig nutzbar.

Benutzer-Einträge überschreiben Built-ins. Werte sind „Respellings“:
so umgeschriebene Wörter, wie sie gesprochen werden sollen.
Bindestriche markieren Silbengrenzen, Großbuchstaben betonte Silben.
Eintrag-Format:
  "Wort": "Ersetzung"                       (für alle Sprachen)
  "Wort": {"de": "…", "en": "…"}            (sprachabhängig)
"""
from __future__ import annotations

import re
import threading
from typing import Dict, List, Optional

from .. import paths
from ..logging_setup import get_logger
from ..utils import read_json, write_json

log = get_logger("pronunciation")

_LOCK = threading.RLock()


class PronunciationDictionary:
    """Verwaltet Built-in- und Benutzer-Aussprachen."""

    def __init__(self):
        self._user: Dict[str, dict] = {}
        self._builtin_de: Dict[str, dict] = {}
        self._builtin_en: Dict[str, dict] = {}
        self._tech_layer: Dict[str, dict] = {}   # Phase 3: Fachwörter
        self._compiled: Optional[dict] = None
        self.load()

    def set_tech_layer(self, mapping: Dict[str, str] | None) -> None:
        """Aktiviert die Fachwort-Germanisierungsebene (Phase 3 §20).

        Priorität bleibt: Benutzer > Fachwort-Layer > Built-ins.
        """
        self._tech_layer = {k: {"repl": v, "match": "insensitive",
                                "priority": 0, "alts": []}
                            for k, v in (mapping or {}).items()}
        self._compiled = None

    # -- Laden/Speichern ----------------------------------------------------
    def load(self) -> None:
        with _LOCK:
            self._user = read_json(paths.PRONUNCIATION_FILE, {}) or {}
            if not isinstance(self._user, dict):
                self._user = {}
            self._builtin_de = read_json(paths.PRONUNCIATION_BUILTINS_DE, {}) or {}
            self._builtin_en = read_json(paths.PRONUNCIATION_BUILTINS_EN, {}) or {}
            # Altes Format migrieren: {"entries": {...}}
            if "entries" in self._user and isinstance(self._user["entries"], dict):
                self._user = self._user["entries"]
            self._compiled = None

    def save(self) -> None:
        with _LOCK:
            write_json(paths.PRONUNCIATION_FILE, self._user)
            self._compiled = None

    # -- CRUD (Anforderung 13) -----------------------------------------------
    def add_entry(self, term: str, value, language: str = "both") -> dict:
        term = term.strip()
        if not term:
            raise ValueError("Leerer Begriff")
        with _LOCK:
            if isinstance(value, str):
                if language == "both":
                    self._user[term] = value
                else:
                    entry = self._user.get(term)
                    if not isinstance(entry, dict):
                        entry = {}
                    entry["de" if language == "de" else "en"] = value
                    self._user[term] = entry
            else:
                self._user[term] = value
            self.save()
        return self._user[term]

    def update_entry(self, term: str, value, language: str = "both") -> dict:
        return self.add_entry(term, value, language)

    def delete_entry(self, term: str) -> bool:
        with _LOCK:
            if term in self._user:
                del self._user[term]
                self.save()
                return True
            return False

    def clear_all(self) -> None:
        """Löscht das komplette BENUTZER-Wörterbuch (Built-ins bleiben)."""
        with _LOCK:
            self._user = {}
            self.save()

    def user_entries(self) -> dict:
        return dict(self._user)

    def builtin_entries(self) -> dict:
        merged = dict(self._builtin_en)
        merged.update(self._builtin_de)
        return merged

    def export_user(self) -> dict:
        return dict(self._user)

    def import_user(self, data: dict, replace: bool = False) -> int:
        with _LOCK:
            if replace:
                self._user = {}
            count = 0
            for k, v in data.items():
                if isinstance(k, str) and isinstance(v, (str, dict)):
                    self._user[k] = v
                    count += 1
            self.save()
            return count

    # -- Anwendung ------------------------------------------------------------
    def _effective_map(self, language: str) -> Dict[str, dict]:
        """Finales Ersetzungsdikt (längste/exakte Begriffe zuerst).

        Phase-1-Fix: Built-ins werden SPRACHGETRENNT geladen (de-Builtins
        inkl. Anglizismen nur für Deutsch, en-Builtins nur für Englisch).
        Benutzer-Einträge überschreiben immer. Erweitertes Format:
        term -> {"repl", "match" (exact|insensitive), "priority", "alts"}.
        """
        lang_key = "de" if language.lower().startswith("ger") else "en"
        cache_key = (f"{lang_key}:{len(self._user)}:"
                     f"{len(self._builtin_de)}:{len(self._builtin_en)}:"
                     f"{len(self._tech_layer)}")
        if self._compiled and self._compiled.get("key") == cache_key:
            return self._compiled["map"]
        result: Dict[str, dict] = {}

        def _put(term: str, value) -> None:
            match_mode = "insensitive"
            priority = 0
            alts: list = []
            repl = value
            if isinstance(value, dict):
                repl = value.get(lang_key) or value.get("de") or value.get("en")
                mm = value.get("match", "insensitive")
                match_mode = mm if mm in ("exact", "insensitive") else "insensitive"
                try:
                    priority = int(value.get("priority", 0))
                except (TypeError, ValueError):
                    priority = 0
                alts = list(value.get("alt", []))
            if isinstance(repl, str) and repl.strip():
                result[term.strip()] = {"repl": repl.strip(),
                                        "match": match_mode,
                                        "priority": priority,
                                        "alts": alts}

        builtin = self._builtin_de if lang_key == "de" else self._builtin_en
        sources = (builtin, self._user)
        if lang_key == "de" and self._tech_layer:
            # deutsche Fachwörter ZWISCHEN Built-ins und Benutzer
            sources = (builtin, self._tech_layer, self._user)
        for source in sources:
            for term, value in source.items():
                if isinstance(term, str) and term:
                    _put(term, value)
        ordered = dict(sorted(
            result.items(),
            key=lambda kv: (kv[1]["match"] != "exact",
                            -(len(kv[0]) + kv[1]["priority"] * 0.01))))
        self._compiled = {"key": cache_key, "map": ordered}
        return ordered

    def active_terms(self, language: str) -> set:
        """Alle aktiven Begriffe (für Namens-Coverage)."""
        return set(self._effective_map(language).keys())

    def coverage_for(self, names: list, language: str) -> dict:
        """Wie viele erkannte Eigennamen sind abgesichert? (Metadaten)"""
        terms = {t.lower() for t in self.active_terms(language)}
        covered = sum(1 for n in names
                      if str(getattr(n, "name", "")).lower() in terms)
        risky = [n for n in names if getattr(n, "risk", False)]
        risky_covered = sum(
            1 for n in risky if str(getattr(n, "name", "")).lower() in terms)
        return {"names_total": len(names), "names_covered": covered,
                "risky_total": len(risky), "risky_covered": risky_covered}

    def apply_to_text(self, text: str, language: str) -> tuple[str, list]:
        """Ersetzt Wörterbuch-Begriffe im Text; gibt (Text, Ersetzungen) zurück."""
        mapping = self._effective_map(language)
        if not mapping:
            return text, []
        replacements: list = []

        def _repl_factory(repl: str, full_text: str, entry: dict | None = None):
            alts = {str(a).lower() for a in (entry or {}).get("alts", [])}

            def _r(m: re.Match) -> str:
                out = m.group(0)
                if out.lower() in alts:
                    return out          # bereits erzeugte Aussprache
                # Großschreibung nur am Satzanfang beibehalten
                before = full_text[max(0, m.start() - 2):m.start()]
                at_start = m.start() == 0 or before.rstrip().endswith(
                    (".", "!", "?", ":", ";", "\n"))
                if at_start and repl[:1].islower():
                    repl_c = repl[0].upper() + repl[1:]
                else:
                    repl_c = repl
                replacements.append({"from": out, "to": repl_c})
                return repl_c
            return _r

        for term, entry in mapping.items():
            if entry["match"] == "exact":
                pattern = re.compile(r"(?<![\wÄÖÜäöüß-])" + re.escape(term) +
                                     r"(?![\wÄÖÜäöüß])")
            else:
                pattern = re.compile(r"(?<![\wÄÖÜäöüß-])" + re.escape(term) +
                                     r"(?![\wÄÖÜäöüß])", re.IGNORECASE)
            text = pattern.sub(_repl_factory(entry["repl"], text, entry), text)
        return text, replacements

    def find_unknown_problem_words(self, text: str, language: str,
                                   max_words: int = 40) -> List[dict]:
        """Schlägt problematische Begriffe vor, die noch KEINEN Eintrag haben
        (Anforderung 14: kontextbezogen prüfen statt raten).

        Deutsche Substantive sind immer großgeschrieben – Satzanfänge und
        sehr häufige Wörter werden daher gefiltert; übrig bleiben echte
        Kandidaten (Namen, Marken, Akronyme, Ungewöhnliches)."""
        mapping = self._effective_map(language)
        candidates: Dict[str, int] = {}
        for m in re.finditer(r"(?<![\wÄÖÜäöüß.])([A-ZÄÖÜ][\wÄÖÜäöüß.-]{2,})"
                             r"(?![\wÄÖÜäöüß])", text):
            w = m.group(1)
            if w.lower() in _STOPWORDS:
                continue
            if any(w == k or w.lower() == k.lower() for k in mapping):
                continue
            candidates[w] = candidates.get(w, 0) + 1
        for m in re.finditer(r"\b[A-ZÄÖÜ]{2,6}\b", text):
            w = m.group(0)
            if not any(w == k for k in mapping):
                candidates[w] = candidates.get(w, 0) + 1
        out = [{"term": w, "occurrences": n}
               for w, n in sorted(candidates.items(),
                                  key=lambda kv: -kv[1])[:max_words]]
        return out


_STOPWORDS = set("""
ich du er sie es wir ihr der die das den dem des ein eine einen einem einer
im in an am auf für von mit zu zum zur bei nach über unter vor hinter neben
zwischen durch gegen ohne um und oder aber denn weil dass wenn als wie so doch
ja nein nicht kein keine mehr nur schon auch noch immer wieder dann jetzt hier
dort was wer wo wann warum weshalb deshalb deswegen außerdem zunächst während
später endlich schluss hierzu dabei darüber damit sowie
chapter kapitel teil part abschnitt
januar februar märz april mai juni juli august september oktober november
dezember january february march april may june july october december
eins zwei drei vier fünf sechs sieben acht neun zehn elf zwölf
mensch menschen geschichte geschichten jahr jahre jahren jahrhundert
zeit zeiten welt leben tag tage nacht nächste frage fragen antwort antworten
beispiel beispiele grund gründe ursache ursachen folge folgen art arten weise
weisen sache sachen ding dinge ort orte stadt städte land länder idee ideen
gedanke gedanken gefühl gefühle sinn sinne kraft kräfte möglichkeit
möglichkeiten wichtig wichtige wichtigsten großen weiteren eigenen ganzen
bestimmten einfach besonderen verschiedenen kleinen alten neuen guten langen
kurzen hohen tiefen weiten nahen fernen zweiten dritten vierten letzten ersten
beiden vielen wenigen allen manche solche andere gleiche gesamte übrige rest
number nummer prozent uhr euro dollar woche monat minute sekunde stunde
augenblick moment sogar vielmehr lediglich außerhalb innerhalb beziehungsweise
""".split())
