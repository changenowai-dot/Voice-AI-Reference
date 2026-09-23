"""Echtes Qwen-A/B/C fuer deutsche Fachwort-Regeln (GPU-Host).

Zweck (Uebergabe Phase 2-5)
---------------------------
Fuer jeden Kandidaten werden DREI Varianten in natuerlichen Saetzen
synthetisiert, damit die Entscheidung gehoert und nicht geraten wird:

  A = aktueller Produktionszustand (Regel aus TECH_TERMS_DE, unveraendert)
  B = Identity / natuerliche deutsche Orthografie  (Phase 6: IDENTITY FIRST)
  C = minimale Alternative (nur wo eine begruendete Form hinterlegt ist)

WICHTIG: Dieses Tool faellt kein akustisches Urteil. Es erzeugt die
Audio-Belege und ein Blind-Arbeitsblatt; gehoert und entschieden wird am
Host. Ohne GPU wird sauber geskippt (kein test_double als Beweis, Phase 2).

Varianten-Erzeugung ueber den PRODUKTIONSMECHANISMUS
----------------------------------------------------
Die Ueberschreibung laeuft ueber das Benutzer-Wörterbuch, also exakt ueber
die dokumentierte Prioritaet "Benutzer > Fachwort-Layer > Built-ins"
(app/pronunciation/engine.py: apply_tech_germanization(skip=user_entries)).
Es wird NICHTS auf Platte geschrieben: die Overrides leben nur im Speicher,
`pronunciation/pronunciation.json` bleibt byte-identisch (wird vom Tool
vor/nach mit SHA256 verifiziert).

Kein neuer Testapparat: Engine-Aufbau, Synthese, WAV-Schreiben und QC werden
aus tools/test_pronunciation_tts.py wiederverwendet.

Aufruf (GPU-Host):
    python tools/test_pronunciation_ab.py --dry-run          # Textmatrix, kein Audio
    python tools/test_pronunciation_ab.py --limit 12         # gestaffelt
    python tools/test_pronunciation_ab.py --only Philosoph --only Physik
    python tools/test_pronunciation_ab.py                    # volle Prioritaetsliste

Ergebnis in output/pronunciation_ab/:
    <begriff>/<A|B|C>_<stimme>_s<NN>.wav
    worksheet.md   Blind-Arbeitsblatt (Reihenfolge randomisiert, Labels neutral)
    key.json       Aufloesung der Blind-Labels (erst NACH dem Hoeren oeffnen)
    results.json   Maschinenlesbar inkl. TTS-Text, QC, Dauer
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(TOOLS_DIR))

from app.pronunciation.dictionary import PronunciationDictionary   # noqa: E402
from app.pronunciation.engine import PronunciationEngine           # noqa: E402
from app.pronunciation.tech_terms import TECH_TERMS_DE             # noqa: E402
from app.text.normalize import normalize_text                      # noqa: E402

# Wiederverwendung der vorhandenen Host-Teststruktur (Phase 3: "Nicht erneut
# einen voellig neuen Testapparat bauen").
import test_pronunciation_tts as _tts                              # noqa: E402

DICT_FILE = PROJECT_ROOT / "pronunciation" / "pronunciation.json"

# ---------------------------------------------------------------------------
# Kandidaten
# ---------------------------------------------------------------------------
# Phase 1 + Phase 8 + Phase 9 aus der Uebergabe, plus die Katalog-Kandidaten.
# Reihenfolge = Hoerprioritaet. Begriffe, die bereits Identity sind, stehen
# bewusst NICHT hier (fuer sie gibt es nichts zu entscheiden).
PRIORITY_CANDIDATES: list[str] = [
    # Phase 8: Familie Philosoph (einzige Phase-1-Familie mit aktiven Respells)
    "Philosoph", "Philosophen", "Philosophin", "Philosophinnen",
    "Philosophie", "philosophisch", "philosophische", "philosophischen",
    "philosophischer", "philosophischem",
    # Phase 9: technische/physikalische Auffaelligkeiten
    "Physik", "Physiker", "physikalisch", "Teilchenphysik", "Kernphysik",
    "Astrophysik", "Thermodynamik", "Entropie", "Energie", "Temperatur",
    "Photonen", "Photon", "Molekül", "Moleküle", "Elektrizität",
    "Gravitation", "Relativitätstheorie", "Elementarteilchen",
    "Wellenlänge", "Frequenz", "Spannung", "Widerstand",
    # Phase 9: Mathematik / Informatik
    "Algebra", "Geometrie", "Analysis", "Integrale", "Integral",
    "Exponentialfunktion", "Funktion", "Funktionen", "Kognition", "kognitiv",
    "Neurotransmitter", "Neuroplastizität", "Software", "Hardware",
    "Netzwerk", "Netzwerke", "Kryptografie", "Mikrochip",
    # Phase 3: uebrige Katalog-Kandidaten
    "Determinismus", "Epistemologie", "Astronomie", "astronomisch",
    "Genetik", "Organismus", "Chemie", "chemisch", "Ableitung",
    "Variable", "Variablen",
]

# Minimale Alternativen (Variante C). Nur wo eine konkret begruendete Form
# existiert - sonst wird C ausgelassen und es bleibt bei A/B.
# BEGRUENDUNG ist jeweils TEXTBEZOGEN (Konsistenz/Kuratierung), kein
# akustisches Urteil: gehoert wird am Host.
# ---------------------------------------------------------------------------
# Familien (Phase 5). A/B/C wird PRO FAMILIE gebildet, nicht pro Einzelwort:
# ein Traegersatz enthaelt oft mehrere Formen derselben Familie
# ("Philosophen und Philosophinnen lesen philosophische Texte"). Wuerde man
# nur EIN Wort auf Identity stellen, bliebe der Rest des Satzes respelled und
# der Vergleich waere vermischt - man koennte nicht hoeren, welche Form die
# Wirkung verursacht. Deshalb werden alle Familienmitglieder gleichzeitig
# umgeschaltet: A = Produktion, B = ganze Familie Identity, C = ganze Familie
# mit der dokumentierten Alternative.
# ---------------------------------------------------------------------------
FAMILIES: dict[str, list[str]] = {
    "Philosoph": [
        "Philosoph", "Philosophen", "Philosophin", "Philosophinnen",
        "Philosophie", "philosophisch", "Philosophisch", "philosophische",
        "philosophischen", "philosophischer", "philosophischem",
    ],
    "Physik": ["Physik", "Physiker", "physikalisch"],
    "Physik_Komposita": ["Astrophysik", "Kernphysik", "Teilchenphysik"],
    "Thermo": ["Thermodynamik", "Entropie", "Temperatur", "Energie", "Energien"],
    "Teilchen_Welle": ["Photon", "Photonen", "Wellenlänge", "Frequenz",
                       "Frequenzen", "Elementarteilchen"],
    "Elektro": ["Elektrizität", "Spannung", "Widerstand", "Gravitation"],
    "Molekuel": ["Molekül", "Moleküle", "Chemie", "chemisch"],
    "Relativitaet": ["Relativitätstheorie"],
    "Mathematik_Kern": ["Algebra", "Geometrie", "Analysis"],
    "Analysis_Kern": ["Integral", "Integrale", "Ableitung", "Variable",
                      "Variablen"],
    "Funktion": ["Funktion", "Funktionen", "Exponentialfunktion"],
    "Kognition": ["Kognition", "kognitiv", "Neurotransmitter",
                  "Neuroplastizität"],
    "Rechner": ["Software", "Hardware", "Netzwerk", "Netzwerke",
                "Kryptografie", "Mikrochip"],
    "Wissenschaft_Allg": ["Astronomie", "astronomisch", "Genetik",
                          "Organismus", "Determinismus", "Epistemologie"],
}


ALTERNATIVES: dict[str, str] = {
    # Die Familie ist intern inkonsistent: "Philosoph" betont die 1. Silbe
    # (FI-lo-sof), "Philosophen"/"Philosophin" betonen die 3. (fi-lo-ZO-*).
    # Der Code-Kommentar in tech_terms.py dokumentiert die Absicht selbst als
    # "Phi-lo-SOF", also mit Betonung auf der letzten Silbe. C folgt der
    # dokumentierten Absicht und dem Muster der Geschwisterregeln.
    "Philosoph": "fi-lo-ZOF",
    # "Philosophinnen" betont die 4. Silbe (fi-lo-zo-FIN-nen), das Singular
    # "Philosophin" die 3. (fi-lo-ZO-fin). C zieht den Plural auf das
    # Singular-Muster.
    "Philosophinnen": "fi-lo-ZO-fin-nen",
    # "Software" -> "SORFT-wär" enthaelt ein R, das im Quellwort nicht
    # vorkommt und durch keine der kuratierten Laut-Substitutionen
    # (ph->f, th->t, qu->kw, x->ks) erklaert ist. Die Geschwisterregeln
    # "Hardware" -> "HARD-wär" und "Firmware" -> "FIRM-wär" behalten den
    # Konsonantencluster korrekt bei. C folgt diesem Muster.
    "Software": "SOFT-wär",
}

# Natuerliche Traegersaetze fuer Begriffe, die im Host-Korpus
# (REGRESSION_SENTENCES) keinen eigenen Satz haben.
TEMPLATES: list[str] = [
    "In diesem Abschnitt geht es um {term} und seine Bedeutung.",
    "{term_cap} ist ein zentraler Begriff in diesem Kapitel.",
    "Wer {term} versteht, kann die folgenden Schritte besser einordnen.",
]


def _sha256(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_engine(overrides: dict[str, str] | None = None) -> PronunciationEngine:
    """Engine mit In-Memory-Override (Benutzer-Wörterbuch-Ebene).

    Bewusst ueber `d._user` und NICHT ueber `add_entry()`: `add_entry()`
    ruft `save()` auf und wuerde die echte, versionierte Benutzerdatei
    `pronunciation/pronunciation.json` veraendern.
    """
    d = PronunciationDictionary()
    d._user = dict(overrides or {})
    d._compiled = None
    return PronunciationEngine(d)


def tts_text(sentence: str, overrides: dict[str, str] | None = None) -> tuple[str, list]:
    """Exakter Produktionspfad: normalize_text + PronunciationEngine.process."""
    eng = make_engine(overrides)
    res = eng.process(normalize_text(sentence, "German"), "German",
                      suggest_unknown=False)
    return res.text, [{"from": r["from"], "to": r["to"],
                       "rule": r.get("rule", "")} for r in res.replacements]


def carrier_sentences(term: str, max_sentences: int = 2) -> list[str]:
    """Natuerliche Saetze fuer den Begriff: zuerst das vorhandene Host-Korpus,
    sonst Templates."""
    hits = [s for s in _tts.REGRESSION_SENTENCES if term.lower() in s.lower()]
    if hits:
        return hits[:max_sentences]
    out = []
    for tpl in TEMPLATES[:max_sentences]:
        out.append(tpl.format(term=term, term_cap=term[:1].upper() + term[1:]))
    return out


def family_overrides(members: list[str], variant: str) -> dict[str, str]:
    """Overrides fuer EINE ganze Familie.

    B  = jedes Familienmitglied auf Identity (natuerliche Orthografie)
    C  = jedes Mitglied, fuer das eine begruendete Alternative hinterlegt
         ist, auf diese Alternative; der Rest bleibt auf Identity, damit C
         gegen B isoliert nur die Alternative testet
    A  = keine Overrides (Produktionszustand)
    """
    if variant == "A":
        return {}
    if variant == "B":
        return {m: m for m in members}
    out = {m: m for m in members}
    for m in members:
        if m in ALTERNATIVES:
            out[m] = ALTERNATIVES[m]
    return out


def family_units(candidates: list[str]) -> list[tuple[str, list[str]]]:
    """Ordnet Kandidaten Familien zu. Begriffe ohne Familie werden zu
    Einwort-Familien, damit die Logik einheitlich bleibt."""
    used: set[str] = set()
    units: list[tuple[str, list[str]]] = []
    for fam, members in FAMILIES.items():
        present = [m for m in members if m in candidates and m in TECH_TERMS_DE]
        if present:
            units.append((fam, present))
            used.update(present)
    for c in candidates:
        if c not in used and c in TECH_TERMS_DE:
            units.append((c, [c]))
    return units


def build_plan(units: list[tuple[str, list[str]]], want: set[str],
               sentences_per_family: int) -> list[dict]:
    """Ein Plan-Eintrag = (Familie, Variante, Satz). Die Overrides gelten fuer
    die ganze Familie, damit der Hoervergleich nicht vermischt wird."""
    plan = []
    for fam, members in units:
        # Saetze sammeln: vorhandenes Host-Korpus zuerst, dann Templates.
        # Ein Satz wird pro Familie nur EINMAL verwendet, auch wenn er mehrere
        # Familienmitglieder enthaelt.
        sents: list[str] = []
        for m in members:
            for s in _tts.REGRESSION_SENTENCES:
                if m.lower() in s.lower() and s not in sents:
                    sents.append(s)
        if not sents:
            head = members[0]
            sents = [tpl.format(term=head, term_cap=head[:1].upper() + head[1:])
                     for tpl in TEMPLATES]
        sents = sents[:sentences_per_family]

        for variant in ("A", "B", "C"):
            if variant not in want:
                continue
            overrides = family_overrides(members, variant)
            if variant == "C" and not any(m in ALTERNATIVES for m in members):
                continue          # keine begruendete Alternative hinterlegt
            for i, sent in enumerate(sents, 1):
                text, repls = tts_text(sent, overrides)
                plan.append({
                    "family": fam, "members": members, "variant": variant,
                    "sentence_index": i, "sentence": sent,
                    "overrides": overrides, "tts_text": text,
                    "replacements": repls,
                    "curated_rules": {m: TECH_TERMS_DE.get(m) for m in members},
                    "alternatives": {m: ALTERNATIVES[m] for m in members
                                     if m in ALTERNATIVES},
                })
    return plan


def clip_stem(item: dict) -> str:
    """Dateiname eines Clips: familie_variante_satz."""
    safe = "".join(c if (c.isalnum() or c in "_-") else "_"
                   for c in item["family"])
    return f"{safe}_{item['variant']}_s{item['sentence_index']:02d}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=PROJECT_ROOT / "output" / "pronunciation_ab")
    ap.add_argument("--only", action="append", default=[],
                    help="Nur diese Begriffe (mehrfach angibbar)")
    ap.add_argument("--all-respells", action="store_true",
                    help="Alle aktiven Respell-Regeln statt der Prioritaetsliste")
    ap.add_argument("--variants", default="A,B,C",
                    help="Welche Varianten (Standard: A,B,C)")
    ap.add_argument("--sentences", type=int, default=2,
                    help="Traegersaetze pro Begriff (Standard: 2)")
    ap.add_argument("--limit", type=int, default=0,
                    help="Nur die ersten N Begriffe (0 = alle)")
    ap.add_argument("--voice", action="append",
                    help="Nur diese Stimme (Standard: beide DE-Regressionstimmen)")
    ap.add_argument("--seed", type=int, default=20260923,
                    help="Seed fuer die Blind-Randomisierung")
    ap.add_argument("--dry-run", action="store_true",
                    help="Nur Textmatrix planen und schreiben, KEIN Audio")
    ap.add_argument("--skip-if-no-gpu", action="store_true")
    args = ap.parse_args()

    want = {v.strip().upper() for v in args.variants.split(",") if v.strip()}
    candidates = ([k for k, v in TECH_TERMS_DE.items() if v != k]
                  if args.all_respells else list(PRIORITY_CANDIDATES))
    if args.only:
        only = {o for o in args.only}
        candidates = [c for c in candidates if c in only] or list(args.only)
    if args.limit:
        candidates = candidates[:args.limit]

    dict_before = _sha256(DICT_FILE)
    units = family_units(candidates)
    plan = build_plan(units, want, args.sentences)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "plan.json").write_text(
        json.dumps({"candidates": candidates,
                    "families": {f: m for f, m in units},
                    "variants": sorted(want), "plan": plan},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")

    # Blind-Labels: Reihenfolge randomisiert, damit beim Hoeren keine
    # Erwartung entsteht (A/B/C waeren sonst psychologisch vorbelastet).
    rnd = random.Random(args.seed)
    order = list(range(len(plan)))
    rnd.shuffle(order)
    labels = {}
    for new_idx, plan_idx in enumerate(order, 1):
        labels[plan_idx] = f"S{new_idx:03d}"
    (args.out / "key.json").write_text(json.dumps(
        {"note": "Erst NACH dem Hoeren oeffnen.",
         "seed": args.seed,
         "key": {labels[i]: {"family": plan[i]["family"],
                             "variant": plan[i]["variant"],
                             "sentence": plan[i]["sentence"],
                             "tts_text": plan[i]["tts_text"]}
                 for i in range(len(plan))}},
        ensure_ascii=False, indent=2), encoding="utf-8")

    # Arbeitsblatt
    lines = ["# Blind-Arbeitsblatt Fachwort-A/B/C (Familienebene)", "",
             "Labels sind neutral und randomisiert. Die Aufloesung steht in "
             "`key.json` - erst nach dem Hoeren oeffnen.", "",
             "Verglichen wird PRO FAMILIE, nicht pro Einzelwort: A = Produktion, "
             "B = ganze Familie Identity, C = ganze Familie mit dokumentierter "
             "Alternative. Nur so ist hoerbar, welche Form die Wirkung verursacht.",
             "",
             f"- Begriffe: **{len(candidates)}** in **{len(units)}** Familien",
             f"- Varianten: **{', '.join(sorted(want))}**",
             f"- Clips insgesamt: **{len(plan)}** "
             f"(× Stimmen, sofern Audio erzeugt wurde)", "",
             "| Label | Datei | Familie/Variante | gehört | besser als A? | Notiz |",
             "|---|---|---|---|---|---|"]
    for i, item in enumerate(plan):
        stem = clip_stem(item)
        lines.append(f"| {labels[i]} | `{stem}.wav` |  | ☐ | ☐ |  |")
    (args.out / "worksheet.md").write_text("\n".join(lines), encoding="utf-8")

    if args.dry_run:
        print(f"DRY-RUN: {len(candidates)} Begriffe, {len(plan)} Clips "
              f"(kein Audio)")
        for i, item in enumerate(plan):
            print(f"  [{labels[i]}] {item['family']} / {item['variant']}")
            print(f"      Satz: {item['sentence']}")
            print(f"      TTS : {item['tts_text']}")
        print(f"\nPlan      : {args.out/'plan.json'}")
        print(f"Worksheet : {args.out/'worksheet.md'}")
        print(f"Key       : {args.out/'key.json'}")
        after = _sha256(DICT_FILE)
        print(f"pronunciation.json unveraendert: {after == dict_before}")
        return 0

    have_cuda = False
    try:
        import torch  # noqa: F401
        have_cuda = torch.cuda.is_available()
    except Exception as e:
        if args.skip_if_no_gpu:
            print(f"SKIP (torch/CUDA nicht verfuegbar): {e}")
            print(f"Plan/Worksheet liegen bereit in {args.out}")
            return 0
        print(f"HINWEIS: torch/CUDA nicht verfuegbar: {e}")
    if not have_cuda:
        print("HINWEIS: keine CUDA-GPU - echte Qwen-Belege sind so nicht "
              "moeglich. Mit --skip-if-no-gpu sauber abbrechen.")
        if args.skip_if_no_gpu:
            return 0

    voices = args.voice or _tts.REGRESSION_VOICES
    results: list[dict] = []
    overall_ok = True
    for voice_id in voices:
        try:
            engine, entry, lang, speaker = _tts._build_engine_for_voice(voice_id)
            engine.load()
        except Exception as e:
            print(f"FAIL engine {voice_id}: {e}")
            overall_ok = False
            continue
        vdir = args.out / voice_id
        vdir.mkdir(parents=True, exist_ok=True)
        for i, item in enumerate(plan):
            wav = vdir / (clip_stem(item) + ".wav")
            ok, elapsed, err, _res, sr = _tts._synth(
                engine, item["tts_text"], "German", speaker, wav)
            qc_ok, dur, peak, rms, qc_err = (False, 0.0, 0.0, 0.0, "")
            if ok:
                qc_ok, dur, peak, rms, qc_err = _tts._qc_check_wav(wav)
            if not (ok and qc_ok):
                overall_ok = False
            rec = dict(item)
            rec.update({"voice_id": voice_id, "label": labels[i],
                        "wav_path": str(wav), "ok": bool(ok and qc_ok),
                        "error": err or qc_err, "duration_s": dur,
                        "peak": peak, "rms": rms, "elapsed_s": elapsed,
                        "sample_rate": sr})
            results.append(rec)
            flag = "OK" if rec["ok"] else "FAIL"
            print(f"  [{flag}] {labels[i]} {item['family']}/{item['variant']} "
                  f"({voice_id}) {dur:.1f}s")
        try:
            engine.unload()
        except Exception:
            pass
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass

    (args.out / "results.json").write_text(json.dumps(
        {"final": "PASS" if overall_ok else "FAIL",
         "dictionary_file_unchanged": _sha256(DICT_FILE) == dict_before,
         "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    after = _sha256(DICT_FILE)
    if after != dict_before:
        print(f"!! WARNUNG: pronunciation.json veraendert "
              f"({dict_before[:12]} -> {after[:12]})")
        overall_ok = False
    print(f"\nFINAL_PRONUNCIATION_AB={'PASS' if overall_ok else 'FAIL'}")
    print(f"Reports in {args.out}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
