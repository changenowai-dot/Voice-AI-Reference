"""Fremd- und Fachwort-Germanisierung (Phase 3, §20 – höchste Priorität).

Problem (Nutzer-Hörtest): Begriffe wie „Kybalion“, „Theorie“,
„Quantentheorie" klingen erkennbar KI-generiert, obwohl der Rest des
deutschen Textes natürlich klingt. Ursachen bei mehrsprachigen TTS-
Modellen: anglisierte Laute (engl. „th" statt deutschem „t"), falsche
Betonung/Silbengrenzen bei Griechisch-/Lateinisch-Stämmen, Zögern bei
seltenen Wörtern.

Lösung: TTS-interne Respellings (nur für die Synthese, der Originaltext
bleibt unverändert, §15) mit
  - Silbentrennung über Bindestriche,
  - BETONUNG über GROSSBUCHSTaben (z. B. „teo-RIE“),
  - sicher deutschen Lautbildern (th→t, ph→f nur kuratiert).

Priorität (§8/§14): Benutzerwörterbuch > Fachwort-Layer > Built-ins >
Modell. Nicht geraten wird nichts: jeder Eintrag ist eine belegte
deutsche Lesart (Duden-/Fachsprache-nah).
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Kuratierte Fach-/Fremdwort-Respellings (Deutsch)
# GROSSBUCHSTABEN = betonte Silbe
# ---------------------------------------------------------------------------
TECH_TERMS_DE: dict[str, str] = {
    # --- direkt vom Nutzer genannt (§20) -----------------------------------
    "Kybalion": "Kü-BA-li-on",
    "Kybalions": "Kü-BA-li-ons",
    "Theorie": "teo-RIE",
    "Theorien": "teo-RI-en",
    "theoretisch": "teo-RI-sch",
    "Theoretiker": "teo-RI-ti-ker",
    "Quantentheorie": "Quan-ten-teo-RIE",
    # --- Physik / Naturwissenschaft ----------------------------------------
    "Quantenmechanik": "Quan-ten-me-CHA-nik",
    "Quantenverschränkung": "Quan-ten-ver-SCHRÄN-kung",
    "Quantenzustand": "Quan-ten-zu-STAND",
    "Quanten": "QUAN-ten",
    "Relativitätstheorie": "Re-la-ti-vi-täts-teo-RIE",
    "Stringtheorie": "String-teo-RIE",
    "Chaostheorie": "CHA-os-teo-RIE",
    "Spieltheorie": "Spiel-teo-RIE",
    "Evolutionstheorie": "E-vo-lu-tions-teo-RIE",
    "Systemtheorie": "Sys-tem-teo-RIE",
    "Informationstheorie": "In-for-ma-tions-teo-RIE",
    "Wahrscheinlichkeit": "WAHR-schein-lich-keit",
    "Entropie": "En-tro-PIE",
    "Energie": "E-NER-gie",
    "Symmetrie": "Sym-met-RIE",
    "Determination": "De-ter-mi-NA-tion",
    "Determinismus": "De-ter-mi-NIS-mus",
    "Indeterminismus": "In-de-ter-mi-NIS-mus",
    "Thermodynamik": "Thermo-dy-NA-mik",
    "Physik": "FY-sik",
    "Physiker": "FY-si-ker",
    "physikalisch": "fy-SI-sch",
    "Metaphysik": "Me-ta-FY-sik",
    "Epistemologie": "E-pis-te-mo-LO-gie",
    "Ontologie": "On-to-LO-gie",
    "Phänomen": "Fä-NO-men",
    "Phänomene": "Fä-NO-me-ne",
    "Phänomenologie": "Fä-no-me-no-LO-gie",
    # --- Philosophie / Geisteswissenschaft ---------------------------------
    "Philosophie": "Fi-lo-so-FIE",
    "philosophisch": "fi-lo-SO-fisch",
    "Philosoph": "Phi-LO-sof",
    "These": "TEE-se",
    "Thesen": "TEE-sen",
    "Antithese": "AN-ti-tee-se",
    "Synthese": "Syn-THE-se",
    "Hypothese": "Hy-PO-the-se",
    "Dialektik": "Di-a-LEK-tik",
    "Hermeneutik": "Her-me-NEU-tik",
    "Existenzialismus": "Ex-is-ten-zi-a-LIS-mus",
    "Nihilismus": "NI-hi-lis-mus",
    "Subjektivität": "Sub-jek-ti-VI-tät",
    "Kognition": "Kog-NI-tion",
    "kognitiv": "kog-NI-tiv",
    "Bewusstsein": "be-WUSST-sein",
    "Intentionalität": "In-ten-tio-na-LI-tät",
    "Kategorie": "Ka-te-GO-rie",
    "Paradigma": "Pa-ra-DIG-ma",
    "paradigmatisch": "pa-ra-dig-MA-tisch",
    "Aporie": "A-po-RIE",
    "Dilemma": "Di-LEM-ma",
    "Empirie": "Em-pi-RIE",
    "empirisch": "em-PI-risch",
    "Ideologie": "I-de-o-LO-gie",
    "Etymologie": "E-ty-mo-LO-gie",
    "Term": "TERM",
    # --- Psychologie / Neurowissenschaft -----------------------------------
    "Psychologie": "Psy-cho-LO-gie",
    "psychologisch": "psy-cho-LO-gisch",
    "Psychiatrie": "Psych-ia-TRIE",
    "Psychoanalyse": "Psy-cho-ana-LY-se",
    "Kognitionspsychologie": "Kog-ni-tions-psy-cho-LO-gie",
    "Neurowissenschaft": "Neu-ro-WIS-sen-schaft",
    "Neurotransmitter": "Neu-ro-trans-MIT-ter",
    "Neuroplastizität": "Neu-ro-plas-ti-ZI-tät",
    "Kognitionswissenschaft": "Kog-ni-tions-wis-sen-SCHAFT",
    "Verhaltensforschung": "Ver-HAL-tens-for-schung",
    # --- Mathematik / Logik -------------------------------------------------
    "Mathematik": "Ma-the-MA-tik",
    "Axiom": "AK-si-om",
    "Axiome": "AK-si-o-me",
    "Theorem": "Te-o-REM",
    "Theoreme": "Te-o-RE-me",
    "Algorithmen": "Al-go-RITH-men",
    "Algorithmus": "Al-go-RITH-mus",
    "Statistik": "Sta-TIS-tik",
    "statistisch": "sta-TIS-tisch",
    "topologisch": "to-po-LO-gisch",
    # --- Ökonomie / Gesellschaft -------------------------------------------
    "Ökonomie": "Ö-ko-NO-mie",
    "ökonomisch": "ö-ko-NO-misch",
    "Idealtypus": "I-deal-TY-pus",
    "Rationalität": "Ra-tio-na-LI-tät",
    "Rationalisierung": "Ra-tio-na-LI-sie-rung",
    "Bürokratie": "Bü-ro-kra-TIE",
    "Modernisierung": "Mo-der-ni-SIE-rung",
    "Globalisierung": "Glo-ba-li-SIE-rung",
}

# Sichere Suffix-Regel: …theorie -> …-teo-RIE (für Komposita)
_THEORIE_SUFFIX = re.compile(r"([A-Za-zäöüß-]+)theorie\b")
_THEORETISCH = re.compile(r"\btheoretisch\b")

# Wörter, die NICHT germanisiert werden (echte Englisch-Wörter im Text)
_KEEP = {"Thriller", "Theory", "Theme"}


def german_tech_map() -> dict[str, str]:
    """Aktive Fachwort-Ebene (nur Deutsch; inkl. Komposita-Ableitungen)."""
    return dict(TECH_TERMS_DE)


def apply_tech_germanization(text: str, language: str = "German",
                             skip: set | None = None) \
        -> tuple[str, list]:
    """Wendet Fachwort-Respellings an (TTS-intern, Original bleibt).

    Reihenfolge innerhalb des Textes: exakte Kuratierung zuerst, danach
    die generische …theorie-Suffixregel (nur für längere Komposita, die
    nicht bereits kuratiert sind).
    """
    if not language.lower().startswith("ger"):
        return text, []
    replacements: list = []
    skip_lower = {s.lower() for s in (skip or set())}
    mapping = {k: v for k, v in TECH_TERMS_DE.items()
               if k.lower() not in skip_lower}

    def _factory(repl: str, full: str):
        def _r(m: re.Match) -> str:
            out = m.group(0)
            before = full[max(0, m.start() - 2):m.start()]
            at_start = m.start() == 0 or before.rstrip().endswith(
                (".", "!", "?", ":", ";", "\n"))
            repl_c = repl[0].upper() + repl[1:] if at_start else repl
            replacements.append({"from": out, "to": repl_c,
                                 "rule": "tech_term"})
            return repl_c
        return _r

    for term in sorted(mapping, key=len, reverse=True):
        if term in _KEEP:
            continue
        pattern = re.compile(r"(?<![\wÄÖÜäöüß-])" + re.escape(term) +
                             r"(?![\wÄÖÜäöüß-])")
        if pattern.search(text):
            text = pattern.sub(_factory(mapping[term], text), text)

    # generische Komposita auf „…theorie“ (nicht kuratiert, >= 8 Zeichen)
    def _comp(m: re.Match) -> str:
        stem = m.group(1)
        if stem[-1] not in "nsvtsr":
            stem = stem + "s" if stem[-1] not in "s" else stem
        repl = f"{stem}-teo-RIE"
        replacements.append({"from": m.group(0), "to": repl,
                             "rule": "tech_suffix"})
        return repl
    text = _THEORIE_SUFFIX.sub(_comp, text)
    return text, replacements


def find_uncovered_tech_terms(text: str, language: str = "German",
                              dictionary_terms: set | None = None) -> list:
    """Meldet Fachwort-Kandidaten OHNE Abdeckung (nicht raten, §13)."""
    if not language.lower().startswith("ger"):
        return []
    dict_terms = {t.lower() for t in (dictionary_terms or set())}
    covered = set(TECH_TERMS_DE) | {k for k in dict_terms}
    suspects = []
    for m in re.finditer(r"\b[A-Za-zÄÖÜäöüß]{7,}\b", text):
        w = m.group(0)
        wl = w.lower()
        if w in covered or wl in covered:
            continue
        if re.search(r"(theorie|ogie|ie\b|ik\b|ität|ismus|ieren|ntisch"
                     r"|metrie|nomie|logie|forschung|wissenschaft"
                     r"|lehre\b|kunde\b|metrik)", wl):
            suspects.append(w)
    return sorted(set(suspects))[:25]
