"""Kaskaden- und Konsistenz-Audit der deutschen Fachwort-Schicht (OFFLINE).

Hintergrund (Übergabe 2026-09, §5.2 / §21 / §33)
-------------------------------------------------
Künstliche Respell-Regeln (Bindestrich + GROSS-Silben) sind nicht nur
potenziell selbst falsch, sie können **nachfolgende Regeln auslösen**:

    "Atomkern"  ->(alt) "A-TOM-kern"  ->(Regel Kern->KERN) "A-TOM-KERN"

Das ist eine Kaskade: der kuratierte Wert einer Regel wird durch eine
andere Regel still überschrieben. Dieser Zustand ist **rein textlich
beweisbar** – er braucht keine Akustik und keine GPU. Ein Kaskaden-Fund
ist deshalb auch ohne Qwen-Hosttest ein harter Beleg im Sinne von §33.

Dieses Tool prüft deterministisch:

  1. KASKADEN     – finaler TTS-Text != kuratierter Wert der Regel
                    (isoliert UND im neutralen Trägersatz).
  2. DOPPELEINTRÄGE – doppelte Literal-Keys in TECH_TERMS_DE, inkl.
                    echter WERT-KONFLIKTE (Python: letzter Key gewinnt
                    still, der erste ist toter Code).
  3. PASS-2-DRIFT – die Tech-Map wird im Produktionspfad ZWEIMAL
                    angewendet (apply_tech_germanization UND über
                    dictionary.set_tech_layer in apply_to_text).
                    Gemessen wird, ob Pass 2 den Pass-1-Output ändert.
  4. DE/EN-ISOLATION (§14) – englische Texte dürfen von der deutschen
                    Fachwort-Schicht nicht berührt werden.
  5. KATALOG-COVERAGE (§24–§29) – welche Begriffe haben eine aktive
                    Respell-Regel (= Host-Testkandidat), welche sind
                    Identity, welche haben gar keine Regel.

Kein TTS, keine GPU, keine Architekturänderung: es wird ausschließlich
der reale Produktionspfad (normalize_text + PronunciationEngine.process)
aufgerufen, exakt wie im GUI-Pfad.

Aufruf:
    python tools/pronunciation_cascade_audit.py [--json PFAD] [--md PFAD]
                                                [--strict]

Exit-Code: 0 = keine Kaskaden/Konflikte, 1 = Befunde (--strict erzwingt
Exit 1 auch bei reinen Coverage-Hinweisen nicht; Befunde sind immer
Kaskaden + Wert-Konflikte + EN-Verletzungen).
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import types
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Headless-Tkinter-Stub (gleiches Muster wie pronunciation_audit.py)
try:  # pragma: no cover
    import tkinter  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover
    class _M(types.ModuleType):
        TclError = type("TclError", (Exception,), {})

        class Tk: pass
        class Frame: pass

        class StringVar:
            def __init__(s, *a, **k): pass
            def get(s): return ""
            def set(s, v): pass

        class BooleanVar:
            def __init__(s, *a, **k): pass
            def get(s): return False
            def set(s, v): pass

        class DoubleVar:
            def __init__(s, *a, **k): return None
            def get(s): return 1.0
            def set(s, v): pass

        NONE = N = S = E = W = CENTER = LEFT = RIGHT = TOP = BOTTOM = ""
        HORIZONTAL = VERTICAL = BOTH = ALL = END = X = Y = ""
        DISABLED = NORMAL = ACTIVE = WORD = ""

        def __getattr__(s, n):
            return lambda *a, **k: None

    for _n in ("tkinter", "tkinter.ttk", "tkinter.filedialog",
               "tkinter.messagebox"):
        sys.modules[_n] = _M(_n)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.pronunciation.engine import PronunciationEngine          # noqa: E402
from app.pronunciation.tech_terms import (TECH_TERMS_DE,          # noqa: E402
                                          apply_tech_germanization)
from app.text.normalize import normalize_text                     # noqa: E402

TECH_TERMS_PATH = PROJECT_ROOT / "app" / "pronunciation" / "tech_terms.py"

# Neutraler Trägersatz. Muss selbst REGELFREI sein (wird verifiziert),
# damit jede Differenz eindeutig auf den eingesetzten Begriff zurückgeht.
CARRIER = "Der Abschnitt nennt {term} und bleibt dabei kurz."

# ---------------------------------------------------------------------------
# Erweiterter Prüf-Katalog (Übergabe §24–§29). Enthält bewusst auch Begriffe
# OHNE Regel:Coverage soll sichtbar machen, was natürlich gesprochen wird.
# ---------------------------------------------------------------------------
CATALOG: dict[str, list[str]] = {
    "User_Hoerbefunde_Prio1": [
        "Daten", "Datensatz", "Datensätze", "Datenbank", "Datenbanken",
        "Datenstruktur", "Datenstrukturen", "Datenverarbeitung",
        "Prozessor", "Prozessoren", "Prozessorleistung",
        "Prozessorarchitektur", "Mikroprozessor",
        "Philosoph", "Philosophen", "Philosophin", "Philosophie",
        "philosophisch",
        "Matrix", "Matrizen", "Matrixrechnung",
        "Erkenntnistheorie", "erkenntnistheoretisch", "Erkenntnis",
        "Erkenntnisgewinn",
        "Logarithmus", "Logarithmen", "logarithmisch", "logarithmische",
        "logarithmischen",
        "Vektor", "Vektoren", "Vektorraum", "Vektorräume",
        "Gleichung", "Gleichungen", "Differentialgleichung",
        "Bewegungsgleichung", "Wellengleichung",
        "Quellcode", "Quellcodes", "Quelltext", "Quelltexte",
        "Metaphysik", "metaphysisch", "metaphysische", "metaphysischen",
        "Ontologie", "ontologisch", "ontologische", "ontologischen",
    ],
    "Regressionsanker": [
        "Atom", "Atome", "Atomkern", "Zelle", "Zellen",
        "Proton", "Protonen", "Neutron", "Neutronen",
        "Mathematik", "mathematisch", "mathematische", "mathematischen",
        "mathematischer", "mathematischem",
        "Algorithmus", "Algorithmen",
        "Quantenphysik", "Quantenmechanik", "Neurowissenschaft",
        "Statistik", "Psychologie", "psychologisch", "Theorie",
        "Wahrscheinlichkeit", "Bewusstsein",
    ],
    "Physik": [
        "Photon", "Photonen", "Wellenlänge", "Frequenz", "Energie",
        "Entropie", "Temperatur", "Teilchen", "Teilchenphysik",
        "Elementarteilchen", "Kernphysik", "Kernfusion", "Kernspaltung",
        "Magnetismus", "Elektromagnetismus", "elektromagnetisch",
        "Elektrizität", "Ladung", "Spannung", "Widerstand",
        "Beschleunigung", "Gravitation", "Relativität",
        "Relativitätstheorie", "Raumzeit", "Thermodynamik", "Impuls",
        "Materie", "Antimaterie", "Radioaktivität", "Strahlung",
        "Wellenfunktion", "Quantenfeld", "Quantenfeldtheorie",
    ],
    "Chemie": [
        "Molekül", "Moleküle", "Chemie", "chemisch", "Element", "Elemente",
        "Reaktion", "Reaktionen", "Katalysator", "Katalyse", "Oxidation",
        "Reduktion", "Säure", "Base", "Basen", "Konzentration", "Lösung",
        "Löslichkeit", "Polymer", "Polymere", "Kohlenstoff", "Sauerstoff",
        "Wasserstoff", "Stickstoff", "Schwefel", "Phosphor", "Natrium",
        "Kalium", "Calcium", "Eisen", "Kupfer", "Elektronenhülle",
    ],
    "Biologie": [
        "Zelle", "Zellen", "Zellkern", "Zellmembran", "Zellteilung",
        "DNA", "RNA", "Gen", "Gene", "Genom", "Genetik", "Chromosom",
        "Chromosomen", "Protein", "Proteine", "Enzym", "Enzyme",
        "Mutation", "Mutationen", "Evolution", "Organismus", "Organismen",
        "Bakterium", "Bakterien", "Virus", "Viren", "Mikrobiologie",
        "Molekularbiologie", "Stoffwechsel", "Metabolismus",
        "Photosynthese", "Nervenzelle",
    ],
    "Astronomie": [
        "Astronomie", "astronomisch", "Kosmologie", "kosmologisch",
        "Universum", "Galaxie", "Galaxien", "Planet", "Planeten",
        "Exoplanet", "Exoplaneten", "Stern", "Sterne", "Supernova",
        "Supernovae", "Schwarzes Loch", "Schwarze Löcher", "Raumzeit",
        "Expansion", "Dunkle Materie", "Dunkle Energie", "Antimaterie",
    ],
    "Mathematik_Statistik": [
        "Algebra", "Geometrie", "Analysis", "Integral", "Integrale",
        "Ableitung", "Ableitungen", "Variable", "Variablen", "Funktion",
        "Funktionen", "Gleichung", "Gleichungen", "Vektor", "Vektoren",
        "Matrix", "Matrizen", "Dimension", "Dimensionen", "Logarithmus",
        "Logarithmen", "Exponentialfunktion", "exponentiell",
        "logarithmisch", "Korrelation", "Regression", "Varianz",
        "Mittelwert", "Standardabweichung", "numerisch",
    ],
    "Informatik_Technik": [
        "Daten", "Datenbank", "Datenbanken", "Datenstruktur", "Prozessor",
        "Prozessoren", "Quellcode", "Quelltext", "Verschlüsselung",
        "Kryptografie", "Kryptographie", "Binärcode", "Software",
        "Hardware", "Simulation", "Parameter", "Netzwerk", "Netzwerke",
        "neuronales Netzwerk", "neuronale Netzwerke",
    ],
    "Neuro_Psychologie": [
        "Neuron", "Neuronen", "Synapse", "Synapsen", "Neurotransmitter",
        "Dopamin", "Serotonin", "Adrenalin", "Cortisol", "Amygdala",
        "Hippocampus", "Neuroplastizität", "Kognition", "kognitiv",
        "Wahrnehmung", "Aufmerksamkeit", "Gedächtnis", "Motivation",
        "Persönlichkeit", "Emotion", "Emotionen", "Verhalten",
        "Unterbewusstsein", "Nervensystem",
    ],
    "Philosophie": [
        "Philosoph", "Philosophen", "Philosophie", "philosophisch",
        "Metaphysik", "metaphysisch", "Ontologie", "ontologisch",
        "Erkenntnistheorie", "erkenntnistheoretisch", "Determinismus",
        "Kausalität", "Rationalismus", "Empirismus", "Materialismus",
        "Idealismus", "Existenz", "Realität", "Wirklichkeit",
        "Epistemologie", "Ethik",
    ],
}

# Begriffe, die in einem natürlichen Satz geprüft werden (Kaskaden treten
# oft erst im Satzkontext auf, z. B. durch Satzanfang-Großschreibung).
SENTENCE_PROBES: dict[str, str] = {
    "Kernphysik": "Die Kernphysik untersucht Kernspaltung und Kernfusion.",
    "Regelungstechnik": "Die Regelungstechnik stabilisiert moderne Anlagen.",
    "Elektrotechnik": "Die Elektrotechnik umfasst Strom und Elektronik.",
    "Nachrichtentechnik": "Die Nachrichtentechnik überträgt Signale.",
    "neuronales Netzwerk": "Ein neuronales Netzwerk lernt aus Beispielen.",
    "neuronale Netzwerke": "Neuronale Netzwerke benötigen viele Daten.",
    "Neuronales Netz": "Ein Neuronales Netz besteht aus vielen Schichten.",
    "Atomkern": "Der Atomkern besteht aus Protonen und Neutronen.",
    "Thermodynamik": "Die Thermodynamik beschreibt Energie und Entropie.",
    "Mikroprozessor": "Der Mikroprozessor führt den Quellcode aus.",
    "Quantenphysik": "Die Quantenphysik beschreibt kleinste Zustände.",
    "Metaphysik": "Die Metaphysik fragt nach dem Sein.",
    "Teilchenphysik": "Die Teilchenphysik erforscht Elementarteilchen.",
    "Astrophysik": "Die Astrophysik beschreibt Sterne und Galaxien.",
    "Kognitionswissenschaft": "Die Kognitionswissenschaft verbindet Disziplinen.",
    "Bewusstseinsforschung": "Die Bewusstseinsforschung ist ein junges Feld.",
}

ENGLISH_PROBES = [
    "The matrix of the processor holds the data.",
    "A neural network learns from many examples.",
    "The physicist studied thermodynamics and entropy.",
    "Philosophy asks about ontology and metaphysics.",
    "The algorithm computes the logarithm of each vector.",
]


@dataclass
class CascadeFinding:
    term: str
    curated: str
    isolated_expected: str
    isolated_actual: str
    carrier_expected: str
    carrier_actual: str
    fired_rules: list = field(default_factory=list)
    kind: str = "cascade"


@dataclass
class DuplicateKeyFinding:
    key: str
    values: list
    lines: list
    conflicting: bool


def _capitalized(repl: str, at_start: bool) -> str:
    """Exakt die Logik aus tech_terms._factory / dictionary._repl_factory."""
    if at_start and repl[:1].islower():
        return repl[0].upper() + repl[1:]
    return repl


def _literal_entries() -> list[tuple[str, str, int]]:
    """Liest TECH_TERMS_DE als AST – erhält dabei Reihenfolge, Zeilennummer
    und DOPPELTE Keys (die ein dict-Literal still verschluckt)."""
    tree = ast.parse(TECH_TERMS_PATH.read_text(encoding="utf-8"))
    out: list[tuple[str, str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign):
            continue
        tgt = getattr(node, "target", None)
        if not isinstance(tgt, ast.Name) or tgt.id != "TECH_TERMS_DE":
            continue
        d = node.value
        if not isinstance(d, ast.Dict):
            continue
        for k, v in zip(d.keys, d.values):
            if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                out.append((str(k.value), str(v.value),
                            int(getattr(k, "lineno", 0))))
    return out


def find_duplicate_keys() -> list[DuplicateKeyFinding]:
    entries = _literal_entries()
    seen: dict[str, list[tuple[str, int]]] = {}
    for k, v, ln in entries:
        seen.setdefault(k, []).append((v, ln))
    findings = []
    for k, occ in seen.items():
        if len(occ) < 2:
            continue
        vals = [v for v, _ in occ]
        findings.append(DuplicateKeyFinding(
            key=k, values=vals, lines=[ln for _, ln in occ],
            conflicting=len(set(vals)) > 1))
    findings.sort(key=lambda f: (not f.conflicting, f.key))
    return findings


def tech_layer_inert() -> dict:
    """Prueft, ob die Tech-Map im Dictionary-Durchlauf ueberhaupt wirkt.

    BEFUND: `_effective_map._put()` liest bei Dict-Werten `value.get("de")`
    bzw. `value.get("en")`, `set_tech_layer()` erzeugt aber `{"repl": ...}`.
    Damit wird jeder Tech-Eintrag verworfen und die Fachwort-Ebene wirkt
    ausschliesslich ueber `apply_tech_germanization()` (EIN Durchlauf).

    Dieser Check ist eine WAECHTER-INVARIANTE: Sollte jemand `_put()`
    irgendwann "reparieren", wird der Tech-Layer im zweiten Durchlauf aktiv
    und die latenten Kaskaden-Paare unten werden sofort zu echten Befunden.
    Der Audit schlaegt dann an, bevor eine Regression in Produktion geht.
    """
    from app.pronunciation.dictionary import PronunciationDictionary
    from app.pronunciation.tech_terms import german_tech_map
    d = PronunciationDictionary()
    d.set_tech_layer(german_tech_map())
    eff = d._effective_map("German")
    builtin = d.builtin_entries()
    user = d.user_entries()
    tech_only = [k for k in TECH_TERMS_DE
                 if k not in builtin and k not in user]
    active = [k for k in tech_only if k in eff]
    return {"tech_only_terms": len(tech_only),
            "active_in_dictionary_pass": len(active),
            "inert": len(active) == 0,
            "examples": active[:10]}


def latent_cascade_pairs() -> list[dict]:
    """Statische Invariante: kein kuratierter Output darf von einer anderen
    Regel rematchbar sein (Wurzel des Kaskaden-Mechanismus, Uebergabe Sec.5.2).

    Geprueft wird gegen das Dictionary-Pass-2-Pattern, weil dessen Lookahead
    Bindestriche erlaubt: ein kuratierter Output wie "Kern-fy-SIK" ist dort
    fuer den Key "Kern" matchbar. Heute ist dieser Pfad inert (siehe
    tech_layer_inert), deshalb zaehlen Treffer nur als WARNUNG - sie werden
    zu harten Befunden, sobald der zweite Durchlauf aktiviert wird.
    """
    from app.pronunciation.tech_terms import _KEEP
    keys = [k for k in TECH_TERMS_DE if k not in _KEEP]
    patterns = {k: re.compile(r"(?<![\wÄÖÜäöüß-])"
                              + re.escape(k)
                              + r"(?=$|[\-.,;:!?)\]\s])", re.IGNORECASE)
                for k in keys}
    out = []
    for victim, repl in TECH_TERMS_DE.items():
        if victim in _KEEP or repl == victim:
            continue
        for other in keys:
            if other == victim:
                continue
            m = patterns[other].search(repl)
            if not m:
                continue
            out.append({
                "victim": victim,
                "curated_output": repl,
                "aggressor": other,
                "aggressor_output": TECH_TERMS_DE[other],
                "result_if_pass2_active":
                    repl[:m.start()] + TECH_TERMS_DE[other] + repl[m.end():],
            })
    out.sort(key=lambda d: (d["victim"], d["aggressor"]))
    return out


def audit_cascades(engine: PronunciationEngine) -> tuple[list[CascadeFinding], str]:
    """Vergleicht kuratierten Wert mit dem tatsächlich produzierten TTS-Text.

    Begriffe, die bereits von `normalize_text` umgeschrieben werden (z. B.
    „K.I." -> „K I."), erreichen die Fachwort-Schicht gar nicht mehr in
    ihrer Originalform. Sie sind keine Kaskaden, sondern vorgelagerte
    Normalisierung, und werden deshalb als `normalized-before-tech`
    gekennzeichnet statt als Befund gezählt.
    """
    # Trägersatz muss inert sein
    inert = CARRIER.format(term="Zzzplatzhalter")
    probe_inert = engine.process(normalize_text(inert, "German"), "German")
    if probe_inert.text != inert:
        raise RuntimeError(
            f"Trägersatz ist NICHT inert: {inert!r} -> {probe_inert.text!r}")

    findings: list[CascadeFinding] = []
    checked = 0
    for term, curated in TECH_TERMS_DE.items():
        checked += 1
        # (a) isoliert, Satzanfang-Großschreibung wie im Produktionspfad
        iso_in = normalize_text(term, "German")
        # Vorgelagerte Normalisierung: wenn der Begriff danach nicht mehr
        # in seiner Originalform vorkommt, ist die Tech-Schicht nicht der
        # Ort der Entscheidung (z. B. Akronym "K.I." -> "K I.").
        if term.lower() not in iso_in.lower():
            findings.append(CascadeFinding(
                term=term, curated=curated,
                isolated_expected=_capitalized(curated, True),
                isolated_actual=engine.process(
                    iso_in, "German", suggest_unknown=False).text,
                carrier_expected="", carrier_actual="",
                fired_rules=[], kind="normalized-before-tech"))
            continue
        iso_res = engine.process(iso_in, "German", suggest_unknown=False)
        iso_expected = _capitalized(curated, True)
        # (b) im neutralen Trägersatz (nicht am Satzanfang)
        car_in_src = CARRIER.format(term=term)
        car_expected = CARRIER.format(term=_capitalized(curated, False))
        car_res = engine.process(normalize_text(car_in_src, "German"),
                                 "German", suggest_unknown=False)
        iso_bad = iso_res.text != iso_expected
        car_bad = car_res.text != car_expected
        if iso_bad or car_bad:
            # Reiner Gross-/Kleinschreibungs-Drift am Wortanfang ist KEIN
            # Befund: die Produktion capitalisiert nur am Satzanfang, ein
            # GROSS-Key mitten im Satz liefert korrekterweise die Kleinform.
            only_case = (
                not iso_bad
                and car_res.text.lower() == car_expected.lower())
            findings.append(CascadeFinding(
                term=term, curated=curated,
                isolated_expected=iso_expected, isolated_actual=iso_res.text,
                carrier_expected=car_expected, carrier_actual=car_res.text,
                fired_rules=[r.get("rule", "") for r in car_res.replacements],
                kind="case-only-drift" if only_case else
                ("cascade" if (iso_bad and car_bad) else "context-drift")))
    order = {"cascade": 0, "context-drift": 1, "case-only-drift": 2,
             "normalized-before-tech": 3}
    findings.sort(key=lambda f: (order.get(f.kind, 9), f.term))
    return findings, str(checked)


def audit_pass2_drift() -> list[dict]:
    """Misst, ob der ZWEITE Durchlauf (dictionary-Tech-Layer) den Output
    des ersten Durchlaufs (apply_tech_germanization) verändert."""
    drift = []
    for term in TECH_TERMS_DE:
        src = CARRIER.format(term=term)
        p1, _ = apply_tech_germanization(normalize_text(src, "German"),
                                         "German")
        eng = PronunciationEngine()
        full = eng.process(normalize_text(src, "German"), "German",
                           suggest_unknown=False)
        if full.text != p1:
            drift.append({"term": term, "pass1": p1, "final": full.text})
    return drift


def audit_en_isolation(engine: PronunciationEngine) -> list[dict]:
    """§14: Deutsche Fachwort-Schicht darf den englischen Pfad nicht berühren."""
    bad = []
    for s in ENGLISH_PROBES:
        norm = normalize_text(s, "English")
        res = engine.process(norm, "English", suggest_unknown=False)
        de_rules = [r for r in res.replacements
                    if str(r.get("rule", "")).startswith("DE_TECH")]
        if de_rules or res.text != norm:
            bad.append({"sentence": s, "final": res.text,
                        "de_tech_rules": [r.get("rule") for r in de_rules]})
    return bad


def coverage_report() -> dict:
    """Katalog-Coverage: aktive Respell-Regeln = Host-Testkandidaten (§15)."""
    respell_pat = re.compile(r"[-]|[A-ZÄÖÜ]{2,}")
    out = {}
    totals = {"terms": 0, "identity": 0, "respell": 0, "no_rule": 0}
    for cat, terms in CATALOG.items():
        rows = []
        for t in terms:
            totals["terms"] += 1
            rule = TECH_TERMS_DE.get(t)
            if rule is None:
                # Fall-Insensitive-Lookup wie die Produktion
                low = {k.lower(): v for k, v in TECH_TERMS_DE.items()}
                rule = low.get(t.lower())
            if rule is None:
                kind = "no_rule"
            elif rule == t:
                kind = "identity"
            elif respell_pat.search(rule):
                kind = "respell"
            else:
                kind = "identity"
            totals[kind] += 1
            rows.append({"term": t, "rule": rule, "kind": kind})
        out[cat] = rows
    return {"categories": out, "totals": totals}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path,
                    default=PROJECT_ROOT / "output" / "cascade_audit.json")
    ap.add_argument("--md", type=Path,
                    default=PROJECT_ROOT / "output" / "cascade_audit.md")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    engine = PronunciationEngine()
    dups = find_duplicate_keys()
    cascades, checked = audit_cascades(engine)
    drift = audit_pass2_drift()
    en_bad = audit_en_isolation(engine)
    cov = coverage_report()

    conflicts = [d for d in dups if d.conflicting]
    # Harte Befunde = echte Kaskaden (kuratierter Wert wird ueberschrieben),
    # Wert-Konflikte und DE/EN-Verletzungen. "case-only-drift" und
    # "normalized-before-tech" sind erklaerte, ungefaehrliche Zustaende.
    real_cascades = [f for f in cascades if f.kind == "cascade"]
    drifts = [f for f in cascades if f.kind == "context-drift"]
    inert = tech_layer_inert()
    latent = latent_cascade_pairs()
    # Latente Paare werden erst zu harten Befunden, wenn der zweite
    # Durchlauf tatsaechlich aktiv ist (heute: inert).
    latent_hard = latent if not inert["inert"] else []
    hard_findings = (len(real_cascades) + len(conflicts) + len(en_bad)
                     + len(drifts) + len(latent_hard))

    report = {
        "final": "PASS" if hard_findings == 0 else "FINDINGS",
        "rules_checked": checked,
        "cascades": [asdict(f) for f in cascades],
        "real_cascades": [asdict(f) for f in real_cascades],
        "latent_cascade_pairs": latent,
        "tech_layer_in_dictionary_pass": inert,
        "duplicate_keys": [asdict(d) for d in dups],
        "conflicting_duplicate_keys": [asdict(d) for d in conflicts],
        "pass2_drift": drift,
        "en_isolation_violations": en_bad,
        "coverage_totals": cov["totals"],
        "coverage": cov["categories"],
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                         encoding="utf-8")

    lines = ["# Kaskaden- & Konsistenz-Audit (offline, deterministisch)", "",
             f"Ergebnis: **{report['final']}**", "",
             f"- geprüfte Regeln: **{checked}**",
             f"- ECHTE Kaskaden: **{len(real_cascades)}**",
             f"- latente Kaskaden-Paare (nur relevant falls Pass 2 aktiv): "
             f"**{len(latent)}**",
             f"- Tech-Layer im Dictionary-Durchlauf: "
             f"**{'inert (1 Durchlauf)' if inert['inert'] else 'AKTIV'}** "
             f"({inert['active_in_dictionary_pass']}/"
             f"{inert['tech_only_terms']} Begriffe wirksam)",
             f"- Kontext-Drifts: **{len(drifts)}**",
             f"- erklaerte Zustaende (case-only / normalize-vor-Tech): "
             f"**{len(cascades) - len(real_cascades) - len(drifts)}**",
             f"- doppelte Literal-Keys: **{len(dups)}** "
             f"(davon Wert-Konflikte: **{len(conflicts)}**)",
             f"- Pass-2-Drifts (Tech-Layer läuft zweimal): **{len(drift)}**",
             f"- DE/EN-Isolationsverletzungen: **{len(en_bad)}**", ""]
    if real_cascades:
        lines += ["## Echte Kaskaden (kuratierter Wert überschrieben)", "",
                  "| Begriff | kuratiert | erwartet | tatsächlich |",
                  "|---|---|---|---|"]
        for f in real_cascades:
            lines.append(f"| {f.term} | `{f.curated}` | "
                         f"`{f.isolated_expected}` | "
                         f"`{f.isolated_actual}` |")
        lines.append("")
    else:
        lines += ["## Echte Kaskaden", "", "Keine. ", ""]
    if latent:
        status = "inert" if inert["inert"] else "AKTIV - HARTER BEFUND"
        lines += [f"## Latente Kaskaden-Paare (Dictionary-Pass, {status})", "",
                  "Nur relevant, falls der zweite Durchlauf je aktiviert wird.",
                  "",
                  "| Opfer | kuratierter Output | Aggressor | Ergebnis dann |",
                  "|---|---|---|---|"]
        for d in latent:
            lines.append(f"| {d['victim']} | `{d['curated_output']}` | "
                         f"`{d['aggressor']}` | "
                         f"`{d['result_if_pass2_active']}` |")
        lines.append("")
    if conflicts:
        lines += ["## Wert-Konflikte (doppelte Keys)", ""]
        for d in conflicts:
            lines.append(f"- `{d.key}` Zeilen {d.lines}: {d.values} "
                         f"-> aktiv ist `{d.values[-1]}`")
        lines.append("")
    if en_bad:
        lines += ["## DE/EN-Isolation verletzt", ""]
        for b in en_bad:
            lines.append(f"- {b['sentence']!r} -> {b['final']!r} "
                         f"{b['de_tech_rules']}")
        lines.append("")
    lines += ["## Coverage", "",
              f"- Begriffe im Katalog: {cov['totals']['terms']}",
              f"- Identity: {cov['totals']['identity']}",
              f"- aktive Respell-Regeln (Host-Testkandidaten): "
              f"{cov['totals']['respell']}",
              f"- ohne Regel (natürliche Lesart): {cov['totals']['no_rule']}",
              ""]
    args.md.parent.mkdir(parents=True, exist_ok=True)
    args.md.write_text("\n".join(lines), encoding="utf-8")

    if not args.quiet:
        print("\n".join(lines))
        print(f"JSON: {args.json}")
        print(f"MD  : {args.md}")
    print(f"FINAL_CASCADE_AUDIT={report['final']}")
    return 0 if hard_findings == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
