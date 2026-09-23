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
