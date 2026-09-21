"""Offline Aussprache-Korpus-Test (Pronunciation-Audit).

Prüft die systematische deutsche Aussprache-Normalisierung:
  - Originaltext → normalize_text → PronunciationEngine → TTS-Text
  - dokumentiert Original, erkannte Regel, transformierten TTS-Text
  - stellt sicher, dass die geforderten Begriffe abgedeckt sind
  - prüft die 4 MATHEMATIK-Regressionssätze (ohne GPU-TTS – dafür
    gibt es tools/test_pronunciation_tts.py, das auf dem GPU-Host läuft).

Echter TTS-Test geschieht separat (--tts Flag / host-only), damit
Offline-CI/Entwicklung ohne CUDA laufen kann.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.pronunciation import PronunciationEngine  # noqa: E402
from app.text.normalize import normalize_text  # noqa: E402


# ---------------------------------------------------------------------------
# Systematischer Korpus – klassifiziert nach Problemgruppe (Anforderung 3 A-G)
# ---------------------------------------------------------------------------
@dataclass
class CorpusEntry:
    term: str            # zu prüfender Begriff
    category: str        # Gruppe (Math / Science / CS / Foreign / Abbrev / Symbol / Compound)
    expected_rule_hint: str = ""   # optionaler Hinweis, welche Regel greifen soll
    must_have_rule_prefix: str = ""  # wenn gesetzt: muss ein Replacement mit diesem Rule-Präfix geben
    must_be_spelled: bool = False   # Akronym muss zu „Buchstabe Buchstabe …“ werden
    must_be_worded: bool = False   # Zahl/Symbol muss zu ausgeschriebenem Wort werden


CORPUS: list[CorpusEntry] = [
    # --- A) Wissenschaft / Mathematik ---------------------------------------
    CorpusEntry("Mathematik", "Math", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("mathematisch", "Math", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("mathematische", "Math", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Geometrie", "Math", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Algebra", "Math", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Analysis", "Math", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Statistik", "Math", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Wahrscheinlichkeit", "Math", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Wahrscheinlichkeitstheorie", "Math", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Gleichung", "Math", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Funktion", "Math", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Integral", "Math", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Differential", "Math", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Algorithmus", "Math", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Algorithmen", "Math", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Variable", "Math", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Koeffizient", "Math", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Exponentialfunktion", "Math", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Logarithmus", "Math", must_have_rule_prefix="DE_TECH"),

    # --- B) Naturwissenschaft / Technik ------------------------------------
    CorpusEntry("Physik", "Science", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("physikalisch", "Science", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Quantenphysik", "Science", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Quantenmechanik", "Science", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Chemie", "Science", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("chemisch", "Science", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Biologie", "Science", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Molekül", "Science", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Proton", "Science", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Elektron", "Science", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Photon", "Science", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Energie", "Science", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Frequenz", "Science", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Resonanz", "Science", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Gravitation", "Science", must_have_rule_prefix="DE_TECH"),

    # --- C) Informatik / KI ------------------------------------------------
    CorpusEntry("künstliche Intelligenz", "CS", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Artificial Intelligence", "CS", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Machine Learning", "CS", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Deep Learning", "CS", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Neural Network", "CS", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Transformer", "CS", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Token", "CS", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Prompt", "CS", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Embedding", "CS", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Inferenz", "CS", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Modell", "CS", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("CUDA", "CS", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Python", "CS", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Software", "CS"),  # absorbiert, keine Ersetzung nötig
    CorpusEntry("Hardware", "CS"),
    CorpusEntry("Algorithmus", "CS", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Datenverarbeitung", "CS", must_have_rule_prefix="DE_TECH"),
    # „System“ ist als Lehnwort längst eingedeutscht (Duden-Standard) –
    # keine Ersetzung erzwungen.
    CorpusEntry("System", "Foreign"),

    # --- Akronyme im CS-Kontext (müssen zu Buchstaben werden) -------------
    CorpusEntry("AI", "CS-Abbrev", must_be_spelled=True),
    CorpusEntry("KI", "CS-Abbrev", must_be_spelled=True),
    CorpusEntry("GPU", "CS-Abbrev", must_be_spelled=True),
    CorpusEntry("CPU", "CS-Abbrev", must_be_spelled=True),

    # --- D) Fremdwörter / Anglizismen --------------------------------------
    CorpusEntry("Community", "Foreign", must_have_rule_prefix="DE_LOAN"),
    CorpusEntry("Content", "Foreign", must_have_rule_prefix="DE_LOAN"),
    CorpusEntry("Creator", "Foreign", must_have_rule_prefix="DE_LOAN"),
    CorpusEntry("Story", "Foreign", must_have_rule_prefix="DE_LOAN"),
    CorpusEntry("Design", "Foreign", must_have_rule_prefix="DE_LOAN"),
    CorpusEntry("Performance", "Foreign", must_have_rule_prefix="DE_LOAN"),
    CorpusEntry("Feature", "Foreign", must_have_rule_prefix="DE_LOAN"),
    CorpusEntry("Update", "Foreign", must_have_rule_prefix="DE_LOAN"),
    CorpusEntry("Workflow", "Foreign", must_have_rule_prefix="DE_LOAN"),
    CorpusEntry("Interface", "Foreign", must_have_rule_prefix="DE_LOAN"),
    CorpusEntry("Online", "Foreign", must_have_rule_prefix="DE_LOAN"),
    CorpusEntry("Offline", "Foreign", must_have_rule_prefix="DE_LOAN"),
    CorpusEntry("Marketing", "Foreign", must_have_rule_prefix="DE_LOAN"),
    CorpusEntry("Business", "Foreign", must_have_rule_prefix="DE_LOAN"),
    CorpusEntry("Mindset", "Foreign", must_have_rule_prefix="DE_LOAN"),
    CorpusEntry("Coaching", "Foreign", must_have_rule_prefix="DE_LOAN"),

    # --- E) Abkürzungen ----------------------------------------------------
    CorpusEntry("CEO", "Abbrev", must_be_spelled=True),
    CorpusEntry("UFO", "Abbrev", must_be_spelled=True),
    CorpusEntry("DNA", "Abbrev", must_be_spelled=True),
    CorpusEntry("RNA", "Abbrev", must_be_spelled=True),
    CorpusEntry("RAM", "Abbrev", must_be_spelled=True),
    CorpusEntry("USB", "Abbrev", must_be_spelled=True),
    CorpusEntry("PDF", "Abbrev", must_be_spelled=True),
    CorpusEntry("API", "Abbrev", must_be_spelled=True),
    CorpusEntry("URL", "Abbrev", must_be_spelled=True),
    CorpusEntry("FAQ", "Abbrev", must_be_spelled=True),

    # --- F) Symbole / Zahlen -----------------------------------------------
    CorpusEntry("%", "Symbol", must_be_worded=True),
    CorpusEntry("&", "Symbol", must_be_worded=True),
    CorpusEntry("=", "Symbol", must_be_worded=True),
    CorpusEntry("°C", "Symbol", must_be_worded=True),

    # --- G) zusammengesetzte Fachwörter ------------------------------------
    CorpusEntry("Quantenfeldtheorie", "Compound", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Wahrscheinlichkeitstheorie", "Compound", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Informationstheorie", "Compound", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Bewusstseinsforschung", "Compound", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Neurowissenschaft", "Compound", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Quantencomputer", "Compound", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Mikroprozessor", "Compound", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Rechenleistung", "Compound", must_have_rule_prefix="DE_TECH"),
    CorpusEntry("Datenverarbeitung", "Compound", must_have_rule_prefix="DE_TECH"),
]


# MATHEMATIK-Regressionssätze (Anforderung 8)
REGRESSION_SENTENCES = [
    "Mathematik ist die Sprache der Zahlen.",
    "Die Mathematik beschreibt Muster, Mengen und Strukturen.",
    "Ein mathematischer Algorithmus kann komplexe Probleme lösen.",
    "Quantenphysik und Mathematik bilden eine wichtige Grundlage moderner Forschung.",
]


@dataclass
class TermResult:
    term: str
    category: str
    tts: str
    rules: list = field(default_factory=list)
    ok: bool = True
    notes: str = ""


@dataclass
class SentenceResult:
    original: str
    tts: str
    replacements: list = field(default_factory=list)
    required_terms: list = field(default_factory=list)
    all_terms_replaced: bool = True
    missing_terms: list = field(default_factory=list)


def _context_sentence(term: str) -> str:
    """Bettet einen Begriff in einen neutralen deutschen Satz ein, damit der
    Normalizer/Pronunciation-Engine echten Kontext bekommt (keine
    Klein-/Großschreibungsartefakte am Satzanfang)."""
    if term in ("%", "&", "=", "°C"):
        return f"Der Wert beträgt 50 {term}."
    if term.isupper() and len(term) <= 4:   # Akronym
        return f"Das {term} wird heute verwendet."
    return f"Das Thema {term} ist wichtig."


def run_corpus(engine: PronunciationEngine) -> tuple[list[TermResult], list[SentenceResult]]:
    term_results: list[TermResult] = []
    for e in CORPUS:
        ctx = _context_sentence(e.term)
        norm = normalize_text(ctx, "German")
        p = engine.process(norm, "German", suggest_unknown=False)
        # Welche Regel hat für diesen Begriff gegriffen? (gematchte
        # Replacement-Einträge, deren from mit dem Begriff übereinstimmt
        # oder in denen der transformierte Begriff den Respelling enthält)
        matched_rules = [
            r.get("rule", "") for r in p.replacements
            if (r.get("from", "").lower() == e.term.lower()
                or e.term.lower() in r.get("from", "").lower()
                or e.term.lower() in r.get("to", "").lower())
        ]
        ok = True
        notes = ""
        # Prüfung „ausgeschriebenes Wort/Spelled“
        tts = p.text
        if e.must_be_spelled:
            spelled = " ".join(e.term)
            if spelled not in tts:
                ok = False
                notes = f"Begriff müsste zu „{spelled}“ buchstabiert werden, aber TTS enthält das nicht"
        elif e.must_be_worded:
            if e.term == "%" and "Prozent" not in tts:
                ok = False; notes = "% muss zu ‚Prozent‘ werden"
            elif e.term == "&" and "und" not in tts:
                ok = False; notes = "& muss zu ‚und‘ werden"
            elif e.term == "=" and "gleich" not in tts:
                ok = False; notes = "= muss zu ‚gleich‘ werden"
            elif e.term == "°C" and "Grad" not in tts:
                ok = False; notes = "°C muss zu ‚Grad Celsius‘ werden"
        elif e.must_have_rule_prefix:
            if not any(r.startswith(e.must_have_rule_prefix) for r in matched_rules):
                # Für Tech/Foreign ist jede DE_-Regel, die den Begriff
                # berührt, ausreichend (kann Tech, Loan oder DICT sein).
                if e.must_have_rule_prefix in ("DE_TECH", "DE_LOAN"):
                    if not any(r.startswith("DE_") for r in matched_rules):
                        ok = False
                        notes = (f"Keine Aussprache-Regel mit Präfix "
                                 f"{e.must_have_rule_prefix!r} oder DE_DICT "
                                 f"hat gegriffen (Regeln: {matched_rules})")
                elif not any(r.startswith("DE_TECH") for r in matched_rules):
                    ok = False
                    notes = (f"Keine Regel mit Präfix {e.must_have_rule_prefix!r} "
                             f"hat gegriffen (Regeln: {matched_rules})")
        term_results.append(TermResult(
            term=e.term, category=e.category, tts=tts,
            rules=matched_rules, ok=ok, notes=notes))

    sent_results: list[SentenceResult] = []
    for s in REGRESSION_SENTENCES:
        norm = normalize_text(s, "German")
        p = engine.process(norm, "German", suggest_unknown=False)
        # In allen 4 MATHEMATIK-Sätzen muss Mathematik/mathematisch/Algorithmus/Quantenphysik
        # mit der Tech-Regel ersetzt werden.
        required = []
        if "Mathematik" in s and "Mathematik" not in s.replace("Die Mathematik", ""):
            pass
        lowered = s.lower()
        for kw in ("mathematik", "mathematisch", "algorithmus",
                   "quantenphysik"):
            if kw in lowered:
                required.append(kw)
        # Prüfen, dass jedes required kw im TTS-Text einen Respelling-
        # Marker hat (mithilfe replacements-Liste):
        matched_from = {r.get("from", "").lower() for r in p.replacements}
        missing = [kw for kw in required if not any(kw in mf for mf in matched_from)]
        sent_results.append(SentenceResult(
            original=s, tts=p.text,
            replacements=[{"from": r["from"], "to": r["to"],
                           "rule": r.get("rule", "")} for r in p.replacements],
            required_terms=required,
            all_terms_replaced=(not missing),
            missing_terms=missing))
    return term_results, sent_results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    log = __import__("logging").getLogger("pronunciation.audit")
    engine = PronunciationEngine()
    t0 = time.perf_counter()
    term_results, sent_results = run_corpus(engine)
    elapsed = time.perf_counter() - t0

    total = len(term_results)
    failed = [r for r in term_results if not r.ok]
    sents_total = len(sent_results)
    sents_failed = [s for s in sent_results if not s.all_terms_replaced]

    # Summary nach Kategorien
    by_cat: dict[str, dict] = {}
    for r in term_results:
        c = by_cat.setdefault(r.category, {"ok": 0, "fail": 0})
        if r.ok:
            c["ok"] += 1
        else:
            c["fail"] += 1

    print(f"=== PRONUNCIATION CORPUS AUDIT ===")
    print(f"Begriffe: {total}, fehlgeschlagen: {len(failed)}")
    for cat, c in sorted(by_cat.items()):
        flag = "OK" if c["fail"] == 0 else "FAIL"
        print(f"  [{flag:4s}] {cat:14s} ok={c['ok']:3d}  fail={c['fail']:3d}")
    print()
    print(f"MATHEMATIK-Regressionssätze: {sents_total}, fehlgeschlagen: {len(sents_failed)}")
    for s in sent_results:
        flag = "OK" if s.all_terms_replaced else "FAIL"
        print(f"  [{flag}] {s.original}")
        if s.missing_terms:
            print(f"         ! fehlende Ersetzungen: {s.missing_terms}")
        if args.verbose:
            print(f"         TTS: {s.tts}")
    if failed:
        print()
        print("FEHLER im Korpus:")
        for r in failed:
            print(f"  [{r.category}] {r.term!r}: {r.notes}")
            print(f"            TTS-Kontext: {r.tts[:160]}")
    print()
    print(f"Dauer: {elapsed*1000:.1f} ms")

    final = "PASS" if not failed and not sents_failed else "FAIL"
    print(f"FINAL_CORPUS_AUDIT={final}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps({
            "final": final,
            "elapsed_s": elapsed,
            "terms": [asdict(r) for r in term_results],
            "sentences": [asdict(s) for s in sent_results],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Report: {args.json_out}")

    return 0 if final == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
