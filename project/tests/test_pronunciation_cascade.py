"""Regression: Kaskaden-Guard der deutschen Fachwort-Schicht.

Hintergrund (Übergabe 2026-09, §5.2 / §21 / §33 / §34)
------------------------------------------------------
Künstliche Respell-Regeln erzeugen über ihre Bindestriche NEUE Wortgrenzen.
Lief die Ersetzungsschleife über den jeweils bereits umgeschriebenen Text,
griffen kurze Teilwort-Regeln in die Outputs längerer Regeln hinein:

    "Kernphysik"        -> "Kern-fy-SIK"          -> "KERN-fy-SIK"
    "Regelungstechnik"  -> "RE-ge-lungs-technik"  -> "RE-ge-lungs-TECH-nik"
    "Kinematik"         -> "Ki-ne-MA-tik"         -> "K I-ne-MA-tik"

Im letzten Fall landete ein buchstabiertes Akronym mitten im Wort – der
TTS-Text war dann garantiert falsch, unabhängig von jeder Akustik. Solche
Kaskaden sind rein textlich beweisbar und brauchen deshalb keinen GPU-Host.

Diese Tests sind OFFLINE, deterministisch und schnell. Sie sichern:
  1. den Kaskaden-Guard (Output einer Regel ist endgültig),
  2. die Regressionsanker aus §7/§34 (bit-identische Aussprache),
  3. dass TECH_TERMS_DE keine Wert-Konflikte durch doppelte Keys hat,
  4. die DE/EN-Isolation (§14),
  5. die Wächter-Invariante, dass der Dictionary-Tech-Layer inert bleibt.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from app.pronunciation import PronunciationEngine
from app.pronunciation.tech_terms import (TECH_TERMS_DE, _KEEP,
                                          apply_tech_germanization)
from app.text.normalize import normalize_text

_TECH_TERMS_PATH = (Path(__file__).resolve().parents[1] / "app"
                    / "pronunciation" / "tech_terms.py")
DICT_PATH = (Path(__file__).resolve().parents[1] / "pronunciation"
             / "pronunciation.json")

# Neutraler Trägersatz, der selbst keine Regel auslöst.
CARRIER = "Der Abschnitt nennt {term} und bleibt dabei kurz."

# §7 / §34: feste Regressionsanker. Diese Begriffe wurden am echten Host mit
# echtem Qwen gehört und für gut befunden. Sie dürfen sich NIE wieder ändern.
REGRESSION_ANCHORS = [
    "Atom", "Atome", "Atomkern", "Zelle", "Zellen",
    "Proton", "Protonen", "Neutron", "Neutronen",
    "Mathematik", "mathematisch", "mathematische", "mathematischen",
    "mathematischer", "mathematischem",
    "Algorithmus", "Algorithmen",
    "Quantenphysik", "Quantenmechanik", "Neurowissenschaft",
    "Statistik", "Psychologie", "psychologisch", "Theorie",
    "Wahrscheinlichkeit", "Bewusstsein",
]

# Erwartete Identity-Ausgabe: natürliche Orthographie, am Satzanfang groß.
ANCHOR_EXPECTED = {t: t for t in REGRESSION_ANCHORS}

# Die drei nachgewiesenen Kaskaden-Opfer: kuratierter Wert muss exakt so
# ankommen, wie er in TECH_TERMS_DE steht.
CASCADE_VICTIMS = ["Kernphysik", "Kinematik", "Regelungstechnik"]


def _engine() -> PronunciationEngine:
    return PronunciationEngine()


def _final(text: str) -> str:
    """Exakter Produktionspfad: normalize_text + PronunciationEngine.process."""
    eng = _engine()
    return eng.process(normalize_text(text, "German"), "German",
                       suggest_unknown=False).text


def test_carrier_is_inert():
    """Der Trägersatz darf selbst keine Regel auslösen (Test-Hygiene)."""
    probe = CARRIER.format(term="Zzzplatzhalter")
    assert _final(probe) == probe


def test_no_cascade_victim_is_remangled():
    """Kern-Guard: kuratierter Output kommt unverändert beim TTS an."""
    for term in CASCADE_VICTIMS:
        curated = TECH_TERMS_DE[term]
        assert curated != term, f"{term} hat keine Respell-Regel mehr?"
        got = _final(CARRIER.format(term=term))
        want = CARRIER.format(term=curated)
        assert got == want, (
            f"KASKADE bei {term!r}: kuratiert {curated!r}, "
            f"erwartet {want!r}, bekommen {got!r}")


def test_kinematik_has_no_spelled_acronym_inside():
    """Explizit: „Ki-ne-MA-tik" darf nie zu „K I-ne-MA-tik" werden."""
    out = _final("Die Kinematik beschreibt Bewegungen von Körpern.")
    assert "K I-ne" not in out
    assert "Ki-ne-MA-tik" in out


def test_kernphysik_keeps_curated_capitalisation():
    out = _final("Die Kernphysik untersucht Kernspaltung und Kernfusion.")
    assert "KERN-fy-SIK" not in out
    assert "Kern-fy-SIK" in out


def test_regelungstechnik_keeps_curated_suffix():
    out = _final("Die Regelungstechnik stabilisiert moderne Anlagen.")
    assert "RE-ge-lungs-TECH-nik" not in out
    assert "RE-ge-lungs-technik" in out


def test_standalone_aggressors_still_work():
    """Der Guard darf die Aggressor-Regeln selbst nicht abschalten."""
    assert "KERN" in _final("Der Kern der Sache ist klar.")
    assert "TECH-nik" in _final("Die Technik ist ausgereift.")
    assert "K I" in _final("KI verändert die Arbeitswelt.")


def test_regression_anchors_identity():
    """§7/§34: Anker bleiben natürliche Orthographie (Identity)."""
    for term in REGRESSION_ANCHORS:
        rule = TECH_TERMS_DE.get(term)
        assert rule == ANCHOR_EXPECTED[term], (
            f"Anker {term!r} hat keine Identity-Regel mehr: {rule!r}")
        # isoliert: Capitalisierung am Satzanfang ist Produktionsverhalten
        # (tech_terms._factory) – erster Buchstabe groß, Rest unverändert.
        want_iso = term[:1].upper() + term[1:]
        assert _final(term) == want_iso, (
            f"Anker {term!r} isoliert verändert: {_final(term)!r}")
        # mitten im Satz: exakt natürliche Orthographie
        got = _final(CARRIER.format(term=term))
        assert got == CARRIER.format(term=term), (
            f"Anker {term!r} im Satz verändert: {got!r}")


def test_bewusstsein_not_resyllabified():
    """§8: „be-WUSST-sein" war ein bestätigter Fehler – darf nicht zurueckkehren."""
    out = _final("Bewusstsein ist aus Sicht der Neurowissenschaft ein Prozess.")
    assert "be-WUSST-sein" not in out
    assert "Bewusstsein" in out


def test_particle_family_identity():
    """§10: Proton/Neutron/Elektron-Familie bleibt Identity."""
    out = _final("Der Atomkern besteht aus Protonen und Neutronen.")
    assert out == "Der Atomkern besteht aus Protonen und Neutronen."
    out2 = _final("Protonen und Neutronen befinden sich im Atomkern, "
                  "Elektronen in der Hülle.")
    assert "Pro-TO-nen" not in out2 and "Noi-tro-NEN" not in out2
    assert "Protonen" in out2 and "Neutronen" in out2


def test_neuronales_netzwerk_single_stage():
    """§21: aufgelöst. „neuronales Netzwerk" wird NUR von der Netzwerk-Regel
    erfasst; die befürchtete zweite Stufe „Neuro-NA-les Netz-werk" tritt
    nicht ein, weil der Lookahead von „Neuronales Netz" in „Netzwerk"
    keine Wortgrenze findet."""
    out = _final("Ein neuronales Netzwerk lernt aus Beispielen.")
    assert out == "Ein neuronales NETZ-werk lernt aus Beispielen."
    assert "Neuro-NA-les Netz-werk" not in out


def test_prozessor_family_identity():
    """§19/§24: Prozessor-Familie – der Cluster „pro-TS-ess-sor" ist weg."""
    for term in ["Prozessor", "Mikroprozessor"]:
        assert TECH_TERMS_DE[term] == term, f"{term} nicht Identity"
    out = _final("Der Mikroprozessor führt den Quellcode aus.")
    assert "TS-ess-sor" not in out
    assert "Mikroprozessor" in out


def test_no_conflicting_duplicate_keys():
    """Ein dict-Literal lässt den letzten Key still gewinnen. Unterschiedliche
    Werte für denselben Key sind toter Code und eine latente Fehlerquelle
    (Befund: „Thermodynamik" stand zweimal mit unterschiedlichem Wert)."""
    tree = ast.parse(_TECH_TERMS_PATH.read_text(encoding="utf-8"))
    entries: list[tuple[str, str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign):
            continue
        tgt = getattr(node, "target", None)
        if not isinstance(tgt, ast.Name) or tgt.id != "TECH_TERMS_DE":
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        for k, v in zip(node.value.keys, node.value.values):
            if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                entries.append((str(k.value), str(v.value),
                                int(getattr(k, "lineno", 0))))
    assert entries, "TECH_TERMS_DE konnte nicht gelesen werden"
    seen: dict[str, list] = {}
    for k, v, ln in entries:
        seen.setdefault(k, []).append((v, ln))
    conflicts = {k: occ for k, occ in seen.items()
                 if len({v for v, _ in occ}) > 1}
    assert not conflicts, f"Wert-Konflikte durch doppelte Keys: {conflicts}"


def test_no_equal_length_case_variant_uppercase_first():
    """Bei gleichlangen Case-Varianten muss der Klein-Key gewinnen, sonst
    erzeugt der Kaskaden-Guard mitten im Satz falsche Großschreibung
    (Befund: „die mathematische Analyse" -> „die Mathematische Analyse")."""
    by_lower: dict[str, list[str]] = {}
    for k in TECH_TERMS_DE:
        by_lower.setdefault(k.lower(), []).append(k)
    for low, variants in by_lower.items():
        if len(variants) < 2 or len({len(v) for v in variants}) != 1:
            continue
        # Gleiches Kriterium wie die Produktion: Keys mit kleinem
        # Anfangsbuchstaben gewinnen. (Nicht `t != t.lower()`, weil
        # Mehrwort-Keys wie „künstliche Intelligenz" innere Großbuchstaben
        # tragen und sonst beide als GROSS zählten.)
        order = sorted(variants, key=lambda t: t[:1].isupper())
        assert not order[0][:1].isupper(), (
            f"Case-Varianten {variants}: Key mit Großbuchstabe würde zuerst "
            f"greifen -> {order}")
        out = _final(CARRIER.format(term=low))
        assert out == CARRIER.format(term=TECH_TERMS_DE[order[0]]), (
            f"{low}: erwartete Kleinform im Satz, bekommen {out!r}")


def test_tech_layer_stays_inert_in_dictionary_pass():
    """WÄCHTER: `set_tech_layer()` erzeugt {"repl": ...}, `_put()` liest aber
    value["de"]/value["en"] – die Tech-Ebene ist im Dictionary-Durchlauf inert.
    Das ist gewollt: genau EIN Durchlauf, deterministisch. Wird `_put()` je
    „repariert", aktiviert das 301 Begriffe in einem zweiten Durchlauf und
    öffnet die latenten Kaskaden wieder. Dieser Test schlägt dann an."""
    from app.pronunciation.dictionary import PronunciationDictionary
    from app.pronunciation.tech_terms import german_tech_map
    d = PronunciationDictionary()
    d.set_tech_layer(german_tech_map())
    eff = d._effective_map("German")
    known = set(d.builtin_entries()) | set(d.user_entries())
    tech_only = [k for k in TECH_TERMS_DE if k not in known]
    active = [k for k in tech_only if k in eff]
    assert not active, (
        "Tech-Layer ist im Dictionary-Durchlauf AKTIV geworden "
        f"({len(active)} Begriffe, z.B. {active[:5]}). Damit läuft die "
        "Fachwort-Ebene zweimal – latent_cascade_pairs() im Audit-Tool "
        "muss dann als harter Befund behandelt werden.")


def test_no_latent_cascade_if_pass2_were_active():
    """Dokumentiert die verbleibenden latenten Paare. Solange der zweite
    Durchlauf inert ist, sind sie ungefährlich – die Liste muss aber bekannt
    und klein bleiben, damit eine Aktivierung nicht blind passiert."""
    keys = [k for k in TECH_TERMS_DE if k not in _KEEP]
    patterns = {k: re.compile(r"(?<![\wÄÖÜäöüß-])" + re.escape(k) +
                              r"(?=$|[\-.,;:!?)\]\s])", re.IGNORECASE)
                for k in keys}
    latent = []
    for victim, repl in TECH_TERMS_DE.items():
        if victim in _KEEP or repl == victim:
            continue
        for other in keys:
            if other != victim and patterns[other].search(repl):
                latent.append((victim, other))
    assert set(latent) <= {("Kernphysik", "Kern"), ("Kinematik", "KI")}, (
        f"Neue latente Kaskaden-Paare: {latent}")


def test_de_en_isolation():
    """§14: Die deutsche Fachwort-Schicht darf den englischen Pfad nicht
    berühren."""
    eng = _engine()
    probes = [
        "The matrix of the processor holds the data.",
        "A neural network learns from many examples.",
        "The physicist studied thermodynamics and entropy.",
        "Philosophy asks about ontology and metaphysics.",
        "The algorithm computes the logarithm of each vector.",
    ]
    for s in probes:
        norm = normalize_text(s, "English")
        res = eng.process(norm, "English", suggest_unknown=False)
        de_rules = [r for r in res.replacements
                    if str(r.get("rule", "")).startswith("DE_TECH")]
        assert not de_rules, f"DE-Regel im EN-Pfad: {de_rules} ({s!r})"
        assert res.text == norm, f"EN-Text verändert: {norm!r} -> {res.text!r}"


def test_english_tech_layer_is_noop():
    """apply_tech_germanization muss für Nicht-Deutsch ein No-Op sein."""
    for lang in ("English", "en", "Französisch"):
        out, repl = apply_tech_germanization(
            "The Atom and its Kernphysik are fine.", lang)
        assert out == "The Atom and its Kernphysik are fine."
        assert repl == []


def test_identity_rules_still_bookkept():
    """Identity-Regeln bleiben aktiv (Replacement-Buchhaltung/Audit/Corpus),
    auch wenn sie die Orthographie nicht ändern."""
    out, repl = apply_tech_germanization(
        "Der Atomkern besteht aus Protonen.", "German")
    fired = {r["rule"] for r in repl}
    assert "DE_TECH_Atomkern" in fired
    assert "DE_TECH_Protonen" in fired
    assert out == "Der Atomkern besteht aus Protonen."


def test_placeholders_never_leak_into_output():
    """Der Kaskaden-Guard maskiert mit Steuerzeichen – die dürfen niemals im
    TTS-Text auftauchen."""
    samples = [
        "Die Kernphysik und die Kinematik sowie die Regelungstechnik.",
        "Ein neuronales Netzwerk verarbeitet Daten in der Datenbank.",
        "Der Atomkern besteht aus Protonen und Neutronen.",
        "Die Thermodynamik beschreibt Energie, Entropie und Temperatur.",
        "Metaphysik, Ontologie und Erkenntnistheorie sind Grundfragen.",
        "KI und GPU beschleunigen die Simulation von Molekülen.",
    ]
    for s in samples:
        out = _final(s)
        assert "\x00" not in out and "\x01" not in out, (
            f"Platzhalter-Leck in {out!r}")


# ---------------------------------------------------------------------------
# Phase 1 / Phase 12 (Uebergabe 2026-09-23): Die vom Nutzer gemeldeten
# Problemfamilien muessen in ALLEN geprüften Formen (Grundform, Plural,
# Flexion, Kompositum) und in mehreren Satzkontexten NATÜRLICHE deutsche
# Orthografie an das TTS übergeben. Das ist der Stand nach den Identity-Fixes
# und darf nicht wieder kippen.
#
# Ausgenommen ist die Philosoph-Familie: sie ist die EINZIGE Phase-1-Familie
# mit noch aktiven Respell-Regeln und wartet auf den echten Qwen-A/B-Beleg
# (tools/test_pronunciation_ab.py). Fuer sie wird hier deshalb nur der
# IST-Zustand fixiert, nicht Natürlichkeit behauptet.
# ---------------------------------------------------------------------------
NATURAL_FAMILIES: dict[str, list[str]] = {
    "Daten": ["Daten", "Datensatz", "Datensätze", "Datenbank", "Datenbanken",
              "Datenstruktur", "Datenstrukturen", "Datenverarbeitung"],
    "Prozessor": ["Prozessor", "Prozessoren", "Prozessorleistung",
                  "Prozessorarchitektur", "Mikroprozessor"],
    "Matrix": ["Matrix", "Matrizen", "Matrixrechnung"],
    "Erkenntnis": ["Erkenntnistheorie", "erkenntnistheoretisch", "Erkenntnis",
                   "Erkenntnisgewinn"],
    "Logarithmus": ["Logarithmus", "Logarithmen", "logarithmisch",
                    "logarithmische", "logarithmischen"],
    "Vektor": ["Vektor", "Vektoren", "Vektorraum", "Vektorräume"],
    "Gleichung": ["Gleichung", "Gleichungen", "Differentialgleichung",
                  "Bewegungsgleichung", "Wellengleichung"],
    "Quellcode": ["Quellcode", "Quellcodes", "Quelltext", "Quelltexte"],
    "Metaphysik": ["Metaphysik", "metaphysisch", "metaphysische",
                   "metaphysischen"],
    "Ontologie": ["Ontologie", "ontologisch", "ontologische", "ontologischen"],
}

# Mehrere Satzkontexte pro Familie (Phase 1: "verschiedene Satzkontexte").
NATURAL_CONTEXTS: dict[str, list[str]] = {
    "Daten": ["Die Daten werden verarbeitet.",
              "Jeder Datensatz besitzt eine Datenstruktur.",
              "Große Datenbanken sortieren Datensätze mit Algorithmen."],
    "Prozessor": ["Der Prozessor führt den Quellcode aus.",
                  "Mehrere Prozessoren teilen sich die Prozessorleistung.",
                  "Die Prozessorarchitektur bestimmt den Takt."],
    "Matrix": ["Eine Matrix kann viele Zahlen darstellen.",
               "Matrizen und Vektoren bilden die lineare Algebra."],
    "Erkenntnis": ["Die Erkenntnistheorie untersucht Wissen.",
                   "Erkenntnistheoretisch bleibt der Erkenntnisgewinn offen."],
    "Logarithmus": ["Der Logarithmus kehrt die Exponentialfunktion um.",
                    "Logarithmen und Exponentialfunktionen sind Umkehrfunktionen.",
                    "Logarithmisch skalierte Achsen zeigen logarithmische Verläufe."],
    "Vektor": ["Ein Vektor besitzt Richtung und Betrag.",
               "Matrizen und Vektoren bilden die Grundlage.",
               "Jeder Vektorraum enthält viele Vektorräume."],
    "Gleichung": ["Eine Gleichung beschreibt einen Zusammenhang.",
                  "Ohne Gleichung keine Beschreibung.",
                  "Die Differentialgleichung ergänzt die Wellengleichung."],
    "Quellcode": ["Der Quellcode eines Programms wird ausgeführt.",
                  "Quellcodes und Quelltexte werden versioniert."],
    "Metaphysik": ["Die Metaphysik fragt nach dem Sein.",
                   "Metaphysische und metaphysischen Fragen bleiben offen."],
    "Ontologie": ["Die Ontologie untersucht, was existiert.",
                  "Ontologische und ontologischen Fragen sind grundlegend."],
}

# Frühere, bestätigte Fehlerformen (Handoff §9/§10/§19). Keine davon darf
# jemals wieder an das TTS übergeben werden.
FORBIDDEN_FORMS = [
    "A-TOM", "A-TO-me", "A-TOM-kern", "TSEL-le", "TSEL-len",
    "Pro-TO-nen", "Noi-tro-NEN", "PRO-ton", "NOI-tron",
    "E-lek-TRON", "E-lek-tro-NEN", "be-WUSST-sein",
    "DA-ten", "DA-ten-ban-ken", "Pro-TS-ess-sor", "KWELL-kod",
    "MA-trix", "VEK-tor", "GLEI-chung", "Lo-ga-RITH-mus",
    "Me-ta-FY-sik", "On-to-LO-gie", "Erkenntnis-teo-RIE",
    "Ma-te-MA-tik",
    # --- Batch 5 (2026-09-23): nach echtem Nutzer-Hörbefund am Qwen-A/B-Lauf
    # auf Identity übernommen. Jede dieser Formen ist belegt ersetzt und darf
    # nicht wieder aktiv werden:
    #   TEIL-chen-fy-sik        „B ist bei Teilchenphysik besser als A"
    #   Ther-mo-dy-NA-mik       „B ist bei Thermodynamik besser als A"
    #   SORFT-wär               „B ist bei Software gut" + objektiver Defekt:
    #                           das R hat im Quellwort keine Entsprechung
    #   A-NA-ly-sis             §6/§7 vom Nutzer als offenes Problem benannt;
    #                           Regel war intern inkonsistent zur übrigen
    #                           Familie (analytisch/Analyse ohne Regel)
    #   E-le-men-TAR-teil-chen  §6/§9 vom Nutzer als offenes Problem benannt;
    #                           5 Bindestriche = stärkste Zerhackung im
    #                           Katalog, Widerspruch zum dokumentierten
    #                           Mechanismus „Bindestrich = Sprechbremse"
    "TEIL-chen-fy-sik", "Ther-mo-dy-NA-mik", "SORFT-wär",
    "A-NA-ly-sis", "E-le-men-TAR-teil-chen",
]


def test_user_reported_families_are_natural():
    """Phase 1/6: gemeldete Familien übergeben natürliche Orthografie."""
    for fam, forms in NATURAL_FAMILIES.items():
        for form in forms:
            # isoliert: natürlich heißt hier „unverändert" ODER „nur am
            # Satzanfang großgeschrieben". Letzteres passiert genau dann, wenn
            # eine (Identity-)Regel feuert; Begriffe OHNE Regel werden gar
            # nicht angefasst und bleiben kleingeschrieben, wie eingegeben.
            got = _final(form)
            allowed = {form, form[:1].upper() + form[1:]}
            assert got in allowed, (
                f"{fam}/{form}: isoliert nicht natürlich "
                f"({got!r} statt einer von {sorted(allowed)!r})")
            # im Satz: case-insensitiv, weil die Form im Quelltext am
            # Satzanfang großgeschrieben sein kann. Ein Respell würde die
            # Zeichenkette zerstören (z. B. „Datenbank" -> „DA-ten-ban-ken")
            # und fällt hier zuverlässig auf.
            for sent in NATURAL_CONTEXTS.get(fam, []):
                if form.lower() not in sent.lower():
                    continue
                out = _final(sent)
                assert form.lower() in out.lower(), (
                    f"{fam}/{form}: im Satz künstlich verändert\n"
                    f"  Satz: {sent!r}\n"
                    f"  TTS : {out!r}")


def test_no_confirmed_bad_form_ever_reaches_tts():
    """§9/§10/§19: historisch bestätigte Fehlerformen in allen Kontexten."""
    sentences = [s for ctx in NATURAL_CONTEXTS.values() for s in ctx]
    sentences += [CARRIER.format(term=t)
                  for forms in NATURAL_FAMILIES.values() for t in forms]
    sentences += [
        "Der Atomkern besteht aus Protonen und Neutronen.",
        "Protonen und Neutronen befinden sich im Atomkern, Elektronen in der Hülle.",
        "Die Zelle ist die kleinste Einheit, und Zellen bilden Gewebe.",
        "Bewusstsein ist aus Sicht der Neurowissenschaft ein Prozess.",
        "Mathematik ist die Sprache der Zahlen.",
        "Ein mathematischer Algorithmus löst komplexe Probleme.",
        # Batch 5: Sätze, die die ersetzten Formen FRÜHER ausgelöst haben.
        # Ohne sie wäre die Prüfung der neuen FORBIDDEN_FORMS zahnlos.
        "Die Teilchenphysik untersucht Elementarteilchen.",
        "Elementarteilchen bilden die Grundlage der modernen Teilchenphysik.",
        "Die Teilchenphysik erforscht Elementarteilchen und ihre Wechselwirkungen.",
        "Die Thermodynamik beschreibt Energie, Entropie und Temperatur.",
        "Die Analysis untersucht Grenzwerte, Ableitungen und Integrale.",
        "Software und Hardware brauchen einen gemeinsamen Parameter.",
        "Die Software läuft stabil auf der vorhandenen Hardware.",
    ]
    for sent in sentences:
        out = _final(sent)
        for bad in FORBIDDEN_FORMS:
            assert bad not in out, (
                f"bestätigte Fehlerform {bad!r} wieder aktiv\n"
                f"  Satz: {sent!r}\n  TTS : {out!r}")


def test_philosoph_family_state_is_pinned():
    """Phase 8: Die Philosoph-Familie ist die einzige Phase-1-Familie mit
    aktiven Respell-Regeln. Solange kein echter Qwen-A/B-Beleg vorliegt, wird
    hier bewusst NICHTS geändert – dieser Test pinnt den IST-Zustand, damit
    eine unbemerkte Änderung auffällt."""
    expected = {
        "Philosoph": "FI-lo-sof",
        "Philosophen": "fi-lo-ZO-fen",
        "Philosophin": "fi-lo-ZO-fin",
        "Philosophinnen": "fi-lo-zo-FIN-nen",
        "Philosophie": "fi-lo-zo-FIE",
        "philosophisch": "fi-lo-ZO-fisch",
        "philosophische": "fi-lo-ZO-fi-sche",
        "philosophischen": "fi-lo-ZO-fi-schen",
        "philosophischer": "fi-lo-ZO-fi-scher",
        "philosophischem": "fi-lo-ZO-fi-schem",
    }
    for term, want in expected.items():
        assert TECH_TERMS_DE.get(term) == want, (
            f"Philosoph-Familie geändert ohne Qwen-Beleg: {term} "
            f"{TECH_TERMS_DE.get(term)!r} statt {want!r} – siehe "
            f"tools/test_pronunciation_ab.py und PRONUNCIATION_BATCH3_REPORT.md")


def test_user_dictionary_file_untouched_by_ab_tooling():
    """Das A/B-Tool darf die versionierte Benutzer-Wörterbuchdatei nie
    verändern (Overrides leben nur im Speicher)."""
    from app.pronunciation.dictionary import PronunciationDictionary
    before = DICT_PATH.read_text(encoding="utf-8") if DICT_PATH.exists() else ""
    d = PronunciationDictionary()
    d._user = {"Philosoph": "Philosoph"}
    d._compiled = None
    eng = PronunciationEngine(d)
    out = eng.process("Der Philosoph fragt.", "German",
                      suggest_unknown=False).text
    assert out == "Der Philosoph fragt."
    after = DICT_PATH.read_text(encoding="utf-8") if DICT_PATH.exists() else ""
    assert before == after, "pronunciation.json wurde verändert"
    assert d.user_entries() == {"Philosoph": "Philosoph"}


# ---------------------------------------------------------------------------
# Batch 5 (2026-09-23): Übernahme belegter Varianten in die Produktion
# ---------------------------------------------------------------------------
# Belegklasse: NUTZER-HÖRBEFUND am echten Qwen-A/B-Lauf (§4) bzw. explizite
# Nutzer-Nennung als offenes Problem (§6) plus objektive textliche
# Inkonsistenz. Orthoepische Theorie allein ist weiterhin kein Beleg (§33).
BATCH5_IDENTITY_TERMS = [
    # (Begriff, alte Respell-Form, Beleg)
    ("Teilchenphysik", "TEIL-chen-fy-sik", "§4 Hörbefund: B besser als A"),
    ("Thermodynamik", "Ther-mo-dy-NA-mik", "§4 Hörbefund: B besser als A"),
    ("Software", "SORFT-wär",
     "§4 Hörbefund: B gut; objektiver Defekt (R ohne Quelle)"),
    ("Analysis", "A-NA-ly-sis",
     "§6/§7 Nutzer-Nennung; Familie intern inkonsistent"),
    ("Elementarteilchen", "E-le-men-TAR-teil-chen",
     "§6/§9 Nutzer-Nennung; 5 Bindestriche = Sprechbremse"),
]

BATCH5_CONTEXTS = {
    "Teilchenphysik": ["Die Teilchenphysik untersucht Elementarteilchen.",
                       "Teilchenphysik ist ein Teilgebiet der Physik."],
    "Thermodynamik": ["Die Thermodynamik beschreibt Wärme und Arbeit.",
                      "Thermodynamik gehört zur klassischen Physik."],
    "Software": ["Die Software läuft auf der Hardware.",
                 "Software und Hardware brauchen einen gemeinsamen Parameter."],
    "Analysis": ["Die Analysis untersucht Grenzwerte und Funktionen.",
                 "Analysis gehört zum ersten Studienjahr."],
    "Elementarteilchen": [
        "Die Teilchenphysik untersucht Elementarteilchen.",
        "Elementarteilchen bilden die Grundlage der modernen Teilchenphysik."],
}


def test_batch5_identity_terms_are_live_in_production():
    """§19/§21A: Die belegten Varianten müssen TATSÄCHLICHT im Produktionspfad
    wirken – nicht nur dokumentiert oder vorbereitet sein."""
    for term, old_form, evidence in BATCH5_IDENTITY_TERMS:
        rule = TECH_TERMS_DE.get(term)
        assert rule == term, (
            f"{term}: Regel ist {rule!r}, erwartet Identity {term!r} "
            f"(Beleg: {evidence})")
        # Isolation
        iso = _final(term)
        assert term in iso, f"{term}: Isolation liefert {iso!r}"
        assert old_form not in iso, (
            f"{term}: alte Form {old_form!r} noch aktiv in {iso!r}")
        # Satzkontexte
        for sent in BATCH5_CONTEXTS[term]:
            out = _final(sent)
            assert term.lower() in out.lower(), (
                f"{term}: in {sent!r} fehlt die natürliche Form -> {out!r}")
            assert old_form not in out, (
                f"{term}: alte Form {old_form!r} in {sent!r} -> {out!r}")


def test_batch5_unjudged_siblings_stay_unchanged():
    """§4/§13: „Nicht blind alles auf B setzen." Geschwister ohne Hörbefund
    und ohne objektiven Defekt bleiben exakt, wie sie sind."""
    pinned = {
        "Hardware": "HARD-wär",          # buchstabentreu, kein Befund
        "Firmware": "FIRM-wär",
        "Middleware": "MID-del-wär",
        "Kernphysik": "Kern-fy-SIK",     # Batch-3-Fix, host-verifiziert
        "Astrophysik": "A-stro-fy-SIK",
        "Elektrodynamik": "E-lek-tro-dy-NA-mik",
        "Algebra": "AL-ge-bra",
        "algebraisch": "al-ge-BRA-isch",
        "Geometrie": "Ge-o-me-TRIE",
        "geometrisch": "ge-o-ME-trisch",
        "Physik": "FY-sik",
        "physikalisch": "fy-SI-sch",
        "Entropie": "En-tro-PIE",
        "Temperatur": "Tem-pe-ra-TUR",
        "Photonen": "Fo-TO-nen",
    }
    for term, want in pinned.items():
        assert TECH_TERMS_DE.get(term) == want, (
            f"{term} ohne Beleg geändert: {TECH_TERMS_DE.get(term)!r} statt "
            f"{want!r}. Für diesen Begriff liegt weder ein Nutzer-Hörbefund "
            f"noch ein objektiver textlicher Defekt vor.")


def test_energie_family_state_is_pinned_until_host_verdict():
    """§10: Energie ausdrücklich NICHT blind verändert.

    Der Nutzer hat Energie als „nicht sicher als Fehler bestätigt" markiert
    und verlangt, erst mehrere echte Qwen-Kontexte zu hören. Der objektiv
    dokumentierte Befund – dasselbe Wort erscheint je nach Satz in zwei Formen,
    weil die Regel nur an Wortgrenzen greift und deshalb in Komposita nie
    wirkt – ist im A/B-Harness als Familie mit allen geforderten Kontexten
    hinterlegt. Dieser Test pinnt den Ist-Zustand, bis der Host entscheidet.
    """
    pinned = {
        "Energie": "E-NER-gie",
        "Energien": "E-NER-gi-en",
    }
    for term, want in pinned.items():
        assert TECH_TERMS_DE.get(term) == want, (
            f"{term} ohne Host-Entscheid geändert: "
            f"{TECH_TERMS_DE.get(term)!r} statt {want!r}. §10 verlangt: "
            f"erst mehrere echte Qwen-Kontexte testen, nicht blind ändern.")
    # Die regellosen Komposita müssen natürlich bleiben – genau das ist die
    # vom Nutzer gehörte Inkonsistenz und der Grund, warum der Entscheid
    # aussteht.
    for compound in ("Lichtenergie", "Energiequelle", "Energieerhaltung",
                     "Energieverbrauch"):
        assert compound not in TECH_TERMS_DE, (
            f"{compound} hat unerwartet eine Regel bekommen")
        out = _final(f"Die {compound} ist hier entscheidend.")
        assert compound in out, f"{compound}: {out!r}"


def test_wellenlaenge_family_state_is_pinned_until_host_verdict():
    """§8: Wellenlänge bleibt offen. Der Nutzer fand A (`WEL-len-län-ge`) und
    auch B (natürliche Orthographie) allein noch nicht ausreichend, verlangt
    also zwingend eine Variante C. Eine nicht gehörte C-Form in die Produktion
    zu schreiben wäre ein Regelwechsel ohne Beleg (§13/§33), deshalb wird hier
    nur der Ist-Zustand gepinnt und C im Harness bereitgestellt."""
    assert TECH_TERMS_DE.get("Wellenlänge") == "WEL-len-län-ge", (
        f"Wellenlänge ohne Host-Entscheid geändert: "
        f"{TECH_TERMS_DE.get('Wellenlänge')!r}")
    # C-Kandidat muss im Harness hinterlegt sein, damit der Host-Lauf ihn
    # tatsächlich synthetisiert.
    import importlib.util
    from pathlib import Path
    path = (Path(__file__).resolve().parents[1] / "tools"
            / "test_pronunciation_ab.py")
    spec = importlib.util.spec_from_file_location("_ab_probe", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.ALTERNATIVES.get("Wellenlänge") == "WEL-len-länge", (
        "Variante C für Wellenlänge fehlt im A/B-Harness (§8)")
    assert "Wellenlänge" in mod.FAMILIES, (
        "Wellenlänge braucht eine eigene Familie, sonst wird das Hörurteil "
        "durch Photon/Frequenz vermischt (§8)")
    assert len(mod.FAMILY_SENTENCES.get("Wellenlänge", [])) >= 4, (
        "§8 verlangt mehrere natürliche Satzkontexte für Wellenlänge")
