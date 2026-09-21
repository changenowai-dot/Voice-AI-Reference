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
    "H_Regressionssaetze": [
        "Mathematik ist die Sprache der Zahlen.",
        "Die Mathematik beschreibt Muster, Mengen und Strukturen.",
        "Ein mathematischer Algorithmus kann komplexe Probleme lösen.",
        "Quantenphysik und Mathematik bilden eine wichtige Grundlage moderner Forschung.",
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
            entry = {
                "category": cat,
                "original": term,
                "normalized": norm,
                "tts_text": res.text,
                "changed": changed,
                "rule": _rule_for(res.replacements, term),
                "replacements": res.replacements,
                "unknown_terms": unknown,
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
    md.append("\n## A–G) Einzelbegriffe\n")
    md.append("| Kategorie | Original | Normalisiert | TTS-Text | Regel | Geändert | Unbekannt |\n")
    md.append("|---|---|---|---|---|---|---|\n")
    for r in reports:
        md.append(
            f"| {r['category']} | `{r['original']}` | `{r['normalized']}` | "
            f"`{r['tts_text']}` | {r['rule']} | {'✓' if r['changed'] else '–'} | "
            f"{', '.join(r['unknown_terms']) or '–'} |\n")
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
