"""Automatischer Aussprache-Korpus-Audit (Offline-Pre-Flight).

Durchläuft den geforderten deutschen Aussprache-Testkorpus
(Wissenschaft/Mathematik, Naturwissenschaft/Technik, Informatik/KI,
Fremdwörter, Abkürzungen, Symbole, zusammengesetzte Fachwörter) und
dokumentiert pro Begriff:
  - original
  - erkannte Regel (DE_TECH/DE_LOAN/DE_DICT/DE_NORM)
  - transformierter TTS-Text
  - Sprache
  - ob eine Ersetzung stattgefunden hat

Dies ist der OFFLINE-Teil (kein TTS). Der echte TTS-Lauf wird in
einer zweiten Stufe auf dem GPU-Host ausgeführt.

Keine Architektur-Änderungen – nutzt ausschließlich die
Produktions-Pipeline (normalize_text + PronunciationEngine.process),
so dass das Ergebnis exakt dem GUI-Pfad entspricht.
"""
from __future__ import annotations

import json
import os
import sys
import time
import types
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Headless-Tkinter-Stub, falls ohne Display/System-Tkinter
try:
    import tkinter  # noqa: F401
except ModuleNotFoundError:
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
            def __init__(s, *a, **k): pass
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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.pronunciation import PronunciationEngine  # noqa: E402
from app.text.normalize import NormalizationReport, normalize_text  # noqa: E402


# ---------------------------------------------------------------------------
# Test-Korpus (Punkte 3 A–G)
# ---------------------------------------------------------------------------
CORPUS: dict[str, list[str]] = {
    "A_Wissenschaft_Mathematik": [
        "Mathematik", "mathematisch", "mathematische",
        "Geometrie", "Algebra", "Analysis", "Statistik",
        "Wahrscheinlichkeit", "Wahrscheinlichkeitstheorie",
        "Gleichung", "Funktion", "Integral", "Differential",
        "Algorithmus", "Algorithmen", "Variable", "Koeffizient",
        "Exponentialfunktion", "Logarithmus",
    ],
    "B_Naturwissenschaft_Technik": [
        "Physik", "physikalisch", "Quantenphysik", "Quantenmechanik",
        "Chemie", "chemisch", "Biologie", "Molekül", "Proton",
        "Elektron", "Photon", "Energie", "Frequenz", "Resonanz",
        "Gravitation",
    ],
    "C_Informatik_KI": [
        "künstliche Intelligenz", "Artificial Intelligence",
        "AI", "KI", "Machine Learning", "Deep Learning",
        "Neural Network", "Transformer", "Token", "Prompt",
        "Embedding", "Inferenz", "Modell", "GPU", "CPU", "CUDA",
        "Python", "Software", "Hardware",
    ],
    "D_Fremdwoerter_Anglizismen": [
        "Community", "Content", "Creator", "Story", "Voice",
        "Design", "Performance", "Feature", "Update", "Workflow",
        "System", "Interface", "Online", "Offline", "Marketing",
        "Business", "Mindset", "Coaching",
    ],
    "E_Abkuerzungen": [
        "AI", "KI", "CEO", "UFO", "DNA", "RNA", "CPU", "GPU",
        "RAM", "USB", "PDF", "API", "URL", "FAQ",
    ],
    "F_Symbole_Zahlen_Einheiten": [
        "50%", "Müller & Söhne", "20 °C", "100 km/h", "9,99 €",
        "2024", "Seite 13", "§ 3", "user@host.de", "#1",
        "3 × 4", "15 ÷ 3", "2 + 3 = 5", "GmbH & Co. KG",
    ],
    "G_Komposita": [
        "Quantenfeldtheorie", "Wahrscheinlichkeitstheorie",
        "Informationstheorie", "Bewusstseinsforschung",
        "Neurowissenschaft", "Quantencomputer", "Mikroprozessor",
        "Rechenleistung", "Datenverarbeitung",
    ],
    # Ab hier: Grosser Fachbegriff-Katalog (Forensik 2026-09, Phase 2/9).
    # Ziel: moeglichst viele allgemeine Fachbegriffe systematisch offline
    # klassifizieren (no rule / identity / respell+Kaskadenrisiko), damit
    # der Host-Qwen-Lauf gezielt die Verdaechtigen hoert. TESTMENGE gross,
    # PRODUKTIONSREGELN klein.
    "I_Physik_Teilchen": [
        "Proton", "Protonen", "Neutron", "Neutronen", "Elektron",
        "Elektronen", "Elektronenhülle", "Molekül", "Moleküle",
        "Molekülstruktur", "Photon", "Photonen", "Quant", "Quanten",
        "Wellenlänge", "Frequenz", "Magnetismus", "elektromagnetisch",
        "Strahlung", "Radioaktivität", "Teilchenphysik", "Kernphysik",
        "Thermodynamik", "Entropie", "Impuls", "Beschleunigung",
        "Spannung", "Widerstand", "Magnetfeld", "Relativität",
        "Relativitätstheorie", "Raumzeit", "Antimaterie",
        "Elementarteilchen", "Gravitation", "Materie",
        "Elektromagnetismus", "Elektrizität", "Kernfusion", "Kernspaltung", "Wellen", "Wellenfunktion", "Quantenfeld", "Temperatur", "Frequenzen", "Energien", "Ladung", "Teilchen",
    ],
    "J_Chemie": [
        "Element", "Elemente", "Sauerstoff", "Wasserstoff", "Stickstoff",
        "Kohlenstoff", "Schwefel", "Phosphor", "Natrium", "Kalium",
        "Calcium", "Katalysator", "Katalyse", "Oxidation", "Reduktion",
        "Polymer", "Konzentration", "Reaktion", "Reaktionen",
        "chemische Bindung", "Löslichkeit",
        "Säure", "Base", "Basen", "Polymere", "Eisen", "Kupfer", "pH-Wert",
    ],
    "K_Biologie_Genetik": [
        "Zellkern", "Zellmembran", "Zellteilung", "Gen", "Gene", "Genom",
        "Genetik", "Chromosom", "Chromosomen", "Protein", "Proteine",
        "Enzym", "Enzyme", "Mutation", "Mutationen", "Evolution",
        "Organismus", "Organismen", "Bakterium", "Bakterien", "Virus",
        "Viren", "Stoffwechsel", "Metabolismus", "Photosynthese",
        "Synapse", "Synapsen", "Hormon", "Hormone", "Immunsystem",
        "Nervenzelle", "Molekularbiologie", "Mikrobiologie",
        "Neurobiologie", "Gewebe",
    ],
    "L_Astronomie_Kosmologie": [
        "Astronomie", "astronomisch", "Kosmologie", "kosmologisch",
        "Universum", "Galaxie", "Galaxien", "Planet", "Planeten",
        "Exoplanet", "Exoplaneten", "Supernova", "Nebel", "Expansion",
        "Dunkle Materie", "Dunkle Energie", "Schwarzes Loch",
        "Schwarze Löcher", "Umlaufbahn", "Lichtjahr",
    ],
    "M_Mathematik_Statistik": [
        "Geometrie", "Algebra", "Analysis", "statistisch",
        "Wahrscheinlichkeitsrechnung", "Variablen", "Funktionen",
        "Gleichung", "Gleichungen", "Integral", "Integrale",
        "Differential", "Ableitung", "Vektor", "Vektoren", "Matrix",
        "Matrizen", "Dimension", "numerisch", "logarithmisch",
        "exponentiell", "Korrelation", "Regression",
        "Standardabweichung", "Mittelwert", "Varianz", "Koeffizient",
        "Logarithmus", "Exponentialfunktion",
        "Ableitungen", "Dimensionen",
    ],
    "N_Neurowissenschaft_Psychologie": [
        "Nervensystem", "Neuron", "Neuronen", "neuronales Netzwerk",
        "Dopamin", "Serotonin", "Adrenalin", "Cortisol", "Amygdala",
        "Hippocampus", "Kognition", "kognitiv", "Wahrnehmung",
        "Aufmerksamkeit", "Unterbewusstsein", "Gedächtnis",
        "Neuroplastizität", "Psychologe", "Psychologin", "Verhalten",
        "Emotion", "Emotionen", "Motivation", "Persönlichkeit",
        "Kognitionswissenschaft", "Verhaltensforschung",
    ],
    "O_Medizin_Grundbegriffe": [
        "Anatomie", "Physiologie", "Herzfrequenz", "Blutdruck",
        "Blutkreislauf", "Organ", "Organe", "Immunität", "Infektion",
        "Entzündung", "Stoffwechsel", "Schmerzrezeptor", "Impfstoff",
    ],
    "P_Geowissenschaft": [
        "Geologie", "geologisch", "Mineral", "Mineralien", "Kristall",
        "Kristalle", "Tektonik", "Plattentektonik", "Vulkan", "Vulkane",
        "Vulkanismus", "Erdbeben", "Erosion", "Sediment", "Atmosphäre",
        "Biosphäre", "Lithosphäre", "Hydrosphäre", "Klimatologie",
        "Klima", "Kontinentaldrift",
    ],
    "Q_Informatik_Technik": [
        "Informatik", "Computer", "Prozessor", "Speicher", "Datenbank",
        "Datenstruktur", "Netzwerk", "Verschlüsselung", "Kryptografie",
        "Kryptographie", "binär", "Byte", "Bytes", "Quellcode",
        "Informationsverarbeitung", "Parameter", "Simulation",
        "Mikrochip", "Halbleiter", "Transistor", "Algorithmik",
        "Prozessoren", "Quelltext", "Quelltexte", "Quellcodes", "Datenstrukturen", "Datenspeicher", "neuronale Netzwerke",
    ],
    "R_Philosophie_Geisteswissenschaften": [
        "Metaphysik", "Ontologie", "Epistemologie", "Erkenntnistheorie",
        "Existenz", "Realität", "Wirklichkeit", "Determinismus",
        "Kausalität", "Ethik", "Moral", "Rationalismus", "Empirismus",
        "Materialismus", "Idealismus", "Nihilismus", "Stoizismus",
        "metaphysisch", "ontologisch", "erkenntnistheoretisch", "Vektorräume",
    ],
    "S_Flexionen_Komposita": [
        "Atomen", "atomar", "atomare", "atomaren", "Protonenstrahlung",
        "Neutronenstrahlung", "Elektronenstrom", "neuronale Netze",
        "Quantenfeldtheorie", "Zellteilung", "Zellkernuntersuchung",
        "Molekularbiologie", "Kernspaltung", "Kernfusion",
        "Teilchenbeschleuniger", "Wellenpartikeldualität",
    ],
    "H_Regressionssaetze": [
        "Mathematik ist die Sprache der Zahlen.",
        "Die Mathematik beschreibt Muster, Mengen und Strukturen.",
        "Ein mathematischer Algorithmus kann komplexe Probleme lösen.",
        "Quantenphysik und Mathematik bilden eine wichtige Grundlage moderner Forschung.",
        # Host-Qwen-Befund 2026-09: Protonen/Neutronen-Respells falsch.
        "Protonen und Neutronen befinden sich im Atomkern.",
        "Ein Proton trägt eine positive Ladung, ein Neutron ist neutral geladen.",
        "Die Atome bestehen aus einem Atomkern und einer Elektronenhülle.",
        "Elektronen bewegen sich in bestimmten Bahnen um den Kern.",
        "Zellen enthalten genetische Informationen im Zellkern.",
        "Die chemische Reaktion verändert die Moleküle.",
        "Enzyme beschleunigen den Stoffwechsel jeder Zelle.",
        "Die Galaxien entfernen sich mit wachsender Geschwindigkeit.",
        "Photosynthese wandelt Licht in chemische Energie um.",
        "Neuronen verschalten sich über Synapsen zu Netzwerken.",
        "Die Plattentektonik verschiebt ganze Kontinente.",
        "Algorithmen sortieren Daten in einer Datenbank.",
        "Die Kausalität ist ein Grundbegriff der Philosophie.",
    ],
}


@dataclass
class TermReport:
    category: str
    original: str
    normalized: str
    tts_text: str
    changed: bool
    replacements: list = field(default_factory=list)
    unknown_terms: list = field(default_factory=list)


def _rule_for(repls: list, original_form: str) -> str:
    # Welchen Regel-Präfix hat die erste Ersetzung, die diesen Term betrifft?
    low = original_form.lower()
    for r in repls:
        if r.get("from", "").lower() == low:
            return r.get("rule", "?")
    return "(none)"


def main() -> int:
    eng = PronunciationEngine()
    out_dir = Path(__file__).resolve().parents[1] / "cache" / "pron_audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    reports: list[dict] = []
    sent_reports: list[dict] = []
    n_total = 0
    n_changed = 0
    n_unknown = 0

    for cat, terms in CORPUS.items():
        for term in terms:
            n_total += 1
            is_sentence = term.endswith(".") or term.endswith("!") or term.endswith("?")
            norm = normalize_text(term, "German", NormalizationReport())
            res = eng.process(norm, "German", suggest_unknown=True)
            changed = (res.text != norm) or (norm != term)
            if changed:
                n_changed += 1
            unknown = [u.get("term") for u in res.unknown_problem_words
                       if u.get("term")]
            # In Sätzen nicht alle "unknowns" als Problem zählen; nur die
            # im Originalwort selbst vorkommenden.
            if not is_sentence:
                n_unknown += len(unknown)
            # Kaskadenpruefung (Phase 6): Wird der bereits ersetzte TTS-
            # Text von einer SPÄTEREN Regel erneut verändert (wie ehemals
            # "A-TOM-kern" -> "A-TOM-KERN" durch Kern->KERN)? Dann ist
            # der Respell instabil (Kaskadenrisiko).
            res2 = eng.process(res.text, "German", suggest_unknown=False)
            cascade = res2.text != res.text
            hyphen_caps = bool(__import__("re").search(
                r"[A-ZÄÖÜ]{2,}(?:-[A-Za-zäöüß]+)+", res.text))
            entry = {
                "category": cat,
                "original": term,
                "normalized": norm,
                "tts_text": res.text,
                "changed": changed,
                "rule": _rule_for(res.replacements, term),
                "replacements": res.replacements,
                "unknown_terms": unknown,
                "cascade": cascade,
                "cascade_text": res2.text if cascade else "",
                "hyphen_caps_respell": hyphen_caps,
            }
            if is_sentence:
                sent_reports.append(entry)
            else:
                reports.append(entry)

    md = []
    md.append("# Aussprache-Korpus Audit (Offline)\n")
    md.append(f"Datum: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    md.append(f"Begriffe gesamt: **{n_total}**\n")
    md.append(f"- Begriffe mit Ersetzung: **{n_changed}**\n")
    md.append(f"- Unabgedeckte Problemwörter: **{n_unknown}**\n")
    n_hyphen = sum(1 for r in reports if r.get("hyphen_caps_respell"))
    n_cascade = sum(1 for r in reports if r.get("cascade"))
    md.append(f"- Begriffe mit Bindestrich-/GROSS-Respell "
              f"(Host-Fehlerklasse): **{n_hyphen}**\n")
    md.append(f"- Kaskaden (Nachverarbeitung veraendert Respell): "
              f"**{n_cascade}**\n")
    md.append("\n## A–G) Einzelbegriffe\n")
    md.append("| Kategorie | Original | TTS-Text | Regel | Respell-Typ | Kaskade |\n")
    md.append("|---|---|---|---|---|---|\n")
    for r in reports:
        typ = ("BINDESTRICH/GROSS" if r.get("hyphen_caps_respell")
               else ("identity" if r["tts_text"] == r["original"]
                     else ("regel" if r["changed"] else "no rule")))
        md.append(
            f"| {r['category']} | `{r['original']}` | "
            f"`{r['tts_text']}` | {r['rule']} | {typ} | "
            f"{'JA: ' + r['cascade_text'] if r.get('cascade') else '–'} |\n")
    md.append("\n## H) Regressions-Sätze (echte GUI-TTS-Texte)\n")
    md.append("| Original | TTS-Text | Ersetzungen |\n|---|---|---|\n")
    for r in sent_reports:
        repl_str = "; ".join(f"{a['from']}→{a['to']}" for a in r["replacements"][:6])
        md.append(f"| {r['original']} | `{r['tts_text']}` | {repl_str} |\n")

    md_path = out_dir / "pronunciation_audit.md"
    md_path.write_text("".join(md), encoding="utf-8")
    json_path = out_dir / "pronunciation_audit.json"
    json_path.write_text(
        json.dumps({"terms": reports, "sentences": sent_reports,
                    "summary": {"total": n_total, "changed": n_changed,
                                "unknown": n_unknown}},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"Wrote {md_path}")
    print(f"Wrote {json_path}")
    print(f"Total terms: {n_total}, changed: {n_changed}, unknown: {n_unknown}")
    return 0 if n_unknown == 0 else 0  # Offline-Audit ist immer OK; unbekannte Begriffe sind nur Hinweise


if __name__ == "__main__":
    sys.exit(main())
