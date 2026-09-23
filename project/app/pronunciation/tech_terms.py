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
    "Theorie": "Theorie",
    # Identity (User-Hoerbefund 2026-09, Host): Erkenntnistheorie lief
    # vorher ueber die generische …theorie-Suffixregel als
    # "Erkenntnis-teo-RIE". Expliziter Eintrag gewinnt gegen die
    # Suffixregel (kuratiert zuerst) und ist Kaskaden-frei.
    "Erkenntnistheorie": "Erkenntnistheorie",
    "Theorien": "teo-RI-en",
    "theoretisch": "teo-RI-sch",
    "Theoretiker": "teo-RI-ti-ker",
    "Quantentheorie": "Quan-ten-teo-RIE",
    # --- Physik / Naturwissenschaft ----------------------------------------
    "Quantenmechanik": "Quantenmechanik",
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
    "Wahrscheinlichkeit": "Wahrscheinlichkeit",
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
    "Metaphysik": "Metaphysik",
    "Epistemologie": "E-pis-te-mo-LO-gie",
    "Ontologie": "Ontologie",
    "Phänomen": "Fä-NO-men",
    "Phänomene": "Fä-NO-me-ne",
    "Phänomenologie": "Fä-no-me-no-LO-gie",
    # --- Philosophie / Geisteswissenschaft ---------------------------------
    # Deutsche Respellings: PH wird als F ausgesprochen, betonte Silbe in
    # GROSSBUCHSTABEN, Silbengrenzen durch Bindestrich. Die Formen sind
    # nah an Duden-Aussprache gewählt (Phi-lo-SOF / fi-lo-zo-FIE), damit
    # Qwen3-TTS nicht das englische /f aɪ/ ("fie") für „phie" erzeugt.
    "Philosophie": "fi-lo-zo-FIE",
    "Philosoph": "FI-lo-sof",
    "Philosophen": "fi-lo-ZO-fen",
    "Philosophin": "fi-lo-ZO-fin",
    "Philosophinnen": "fi-lo-zo-FIN-nen",
    "philosophisch": "fi-lo-ZO-fisch",
    "Philosophisch": "Fi-lo-ZO-fisch",
    "philosophischer": "fi-lo-ZO-fi-scher",
    "philosophischem": "fi-lo-ZO-fi-schem",
    "philosophischen": "fi-lo-ZO-fi-schen",
    "philosophische": "fi-lo-ZO-fi-sche",
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
    # Identity-Mapping (bewusst, Muster wie Mathematik-Familie):
    # Das Bindestrich-Respelling "be-WUSST-sein" fuehrte im echten Qwen-
    # Produktionspfad zu ueberartikulierter Betonung ("Be-WUUStsein").
    # Bindestrich = Sprechbremse, GROSS-Silbe kippt in Buchstabier-Modus
    # (A/B-Nachweis des Fehlerbilds: tools/test_pacing_math_ab_tts.py).
    # "Bewusstsein" ist ein normales deutsches Wort; die Regel bleibt
    # aktiv (Replacement-Buchhaltung/Audit/Corpus), setzt aber die
    # NATUERLICHE Orthographie ein. Genitiv "Bewusstseins" matcht per
    # Wortgrenze bewusst nicht und wird natuerlich gesprochen.
    "Bewusstsein": "Bewusstsein",
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
    "Psychologie": "Psychologie",
    "psychologisch": "psychologisch",
    "Psychiatrie": "Psych-ia-TRIE",
    "Psychoanalyse": "Psy-cho-ana-LY-se",
    "Kognitionspsychologie": "Kog-ni-tions-psy-cho-LO-gie",
    "Neurowissenschaft": "Neurowissenschaft",
    "Neurotransmitter": "Neu-ro-trans-MIT-ter",
    "Neuroplastizität": "Neu-ro-plas-ti-ZI-tät",
    "Kognitionswissenschaft": "Kog-ni-tions-wis-sen-SCHAFT",
    "Verhaltensforschung": "Ver-HAL-tens-for-schung",
    # --- Mathematik / Logik -------------------------------------------------
    # Regel-ID: DE_MATH_001 .. DE_MATH_0xx
    # Identity-Mapping (bewusst): Die frueheren Bindestrich-Respellings
    # ("Ma-te-MA-tik") fuehrten zu segmentierter, "buchstabierender"
    # Aussprache in Qwen (Bindestrich = Sprechbremse, GROSS-Silben
    # kippen in Buchstabier-Modus). "Mathematik" ist ein normales
    # deutsche Wort und wird ohne kuenstliche Silbentrennung fluessig
    # gesprochen. Die Regel bleibt aktiv (Replacement-Buchhaltung/
    # Audit/Corpus), setzt aber die NATUERLICHE Orthographie ein.
    # A/B-Nachweis: tools/test_pacing_math_ab_tts.py (Host, GPU).
    "Mathematik": "Mathematik",
    "mathematisch": "mathematisch",
    "Mathematische": "Mathematische",
    "mathematische": "mathematische",
    "mathematischen": "mathematischen",
    "mathematischer": "mathematischer",
    "mathematischem": "mathematischem",
    "Geometrie": "Ge-o-me-TRIE",
    "geometrisch": "ge-o-ME-trisch",
    "Algebra": "AL-ge-bra",
    "algebraisch": "al-ge-BRA-isch",
    "Analysis": "A-NA-ly-sis",
    "Analysis": "A-NA-ly-sis",
    "Statistik": "Statistik",
    "statistisch": "sta-TIS-tisch",
    "Wahrscheinlichkeit": "Wahrscheinlichkeit",
    "Wahrscheinlichkeitstheorie": "WAHR-schein-lich-keits-teo-RIE",
    "Gleichung": "Gleichung",
    "Gleichungen": "Gleichungen",
    "Funktion": "Funk-zi-ON",
    "Funktionen": "Funk-tzi-O-nen",
    "Integral": "In-te-GRAL",
    "Integrale": "In-te-GRA-le",
    "Integration": "In-te-gra-ti-ON",
    "Differential": "Dif-fe-ren-zi-AL",
    "Differenzial": "Dif-fe-ren-tsi-AL",
    "Ableitung": "AP-lei-tung",
    "Algorithmen": "Algorithmen",
    "Algorithmus": "Algorithmus",
    "Variable": "Va-ri-A-ble",
    "Variablen": "Va-ri-A-blen",
    "Koeffizient": "Ko-ef-fi-tsi-ENT",
    "Koeffizienten": "Ko-ef-fi-tsi-EN-ten",
    "Exponentialfunktion": "Eks-po-nen-zi-al-funk-tsi-ON",
    "Logarithmus": "Logarithmus",
    "Logarithmen": "Logarithmen",
    "Logarithmisch": "Logarithmisch",
    "logarithmisch": "logarithmisch",
    "Vektor": "Vektor",
    "Vektoren": "Vektoren",
    "Matrix": "Matrix",
    "Matrizen": "Matrizen",
    "Vektorraum": "Vektorraum",
    "Topologie": "To-po-lo-GIE",
    "topologisch": "to-po-LO-gisch",
    "Mengenlehre": "MEN-gen-leh-re",
    "Zahlentheorie": "TSAH-len-teo-RIE",
    "Wahrscheinlichkeitsrechnung": "WAHR-schein-lich-keits-rech-nung",
    "Axiom": "AK-si-om",
    "Axiome": "AK-si-o-me",
    "Theorem": "Te-o-REM",
    "Theoreme": "Te-o-RE-me",
    "Beweis": "Be-WEIS",
    "Beweise": "Be-WEI-se",
    "Korollar": "Ko-rol-LAR",
    "Lemma": "LEM-ma",
    "Vermutung": "Ver-MU-tung",
    "Hypothese": "Hy-PO-the-se",
    # --- Naturwissenschaft / Physik / Chemie / Biologie --------------------
    "Physik": "FY-sik",
    "Physiker": "FY-si-ker",
    "physikalisch": "fy-SI-sch",
    "Quantenphysik": "Quantenphysik",
    "Quantenmechanik": "Quantenmechanik",
    "Quantenfeldtheorie": "KUAN-ten-felds-teo-RIE",
    "Quantencomputer": "KUAN-ten-com-pju-ter",
    "Chemie": "CE-mie",
    "chemisch": "CE-misch",
    "Chemiker": "CE-mi-ker",
    "Biologie": "Bio-lo-GIE",
    "biologisch": "bio-LO-gisch",
    "Biologe": "Bi-o-LO-ge",
    "Molekül": "Mo-le-KÜHL",
    "Moleküle": "Mo-le-KÜH-le",
    # Identity-Mappings (bewusst, Muster Mathematik/Atom/Zelle):
    # Host-Qwen-Befund (echte GPU, 2026-09): "Der Atomkern besteht aus
    # Pro-TO-nen und Noi-tro-NEN." - die Bindestrich-/GROSS-Respells
    # loesen den nachweislichen Buchstabier-Modus aus. Identity-Mapping
    # der gesamten Teilchenfamilie; Regeln bleiben aktiv (Buchhaltung/
    # Audit/Corpus). Elektron/Elektronen teilen den Mechanismus und
    # werden im naechsten Host-Satzlauf mitverifiziert.
    "Proton": "Proton",
    "Protonen": "Protonen",
    "Elektron": "Elektron",
    "Elektronen": "Elektronen",
    "Neutron": "Neutron",
    "Neutronen": "Neutronen",
    "Photon": "FO-ton",
    "Photonen": "Fo-TO-nen",
    "Energie": "E-NER-gie",
    "Energien": "E-NER-gi-en",
    "Frequenz": "Fre-KWENZ",
    "Frequenzen": "Fre-KWEN-zen",
    "Resonanz": "Re-so-NANZ",
    "Resonanzen": "Re-so-NAN-zen",
    "Gravitation": "Gra-vi-ta-tsi-ON",
    "Gravitationskraft": "Gra-vi-ta-tsi-ONS-kraft",
    "Schwerkraft": "SCHWER-kraft",
    "Relativitätstheorie": "Re-la-ti-vi-täts-teo-RIE",
    "Thermodynamik": "Ther-mo-dy-NA-mik",
    "Elektrodynamik": "E-lek-tro-dy-NA-mik",
    "Quantenchemie": "KUAN-ten-ce-mie",
    "Astrophysik": "A-stro-fy-SIK",
    "Kernphysik": "Kern-fy-SIK",
    "Teilchenphysik": "TEIL-chen-fy-sik",
    # Identity-Mappings (bewusst, Muster wie Mathematik/Bewusstsein):
    # Die Bindestrich-Respells "A-TOM"/"A-TO-me"/"A-TOM-kern" fuehrten im
    # echten Qwen-Produktionspfad zu ueberartikulierter/falscher Aussprache
    # (Nutzer-Hoerbefund; Bindestrich = Sprechbremse, GROSS-Silben kippen
    # in Buchstabier-Modus, A/B-Nachweis des Mechanismus:
    # tools/test_pacing_math_ab_tts.py + tools/test_pronunciation_tts.py).
    # Die Regeln bleiben aktiv (Replacement-Buchhaltung/Audit/Corpus),
    # setzen aber die NATUERLICHE Orthographie ein. Flexionen (atomar,
    # atomare, ...) haben bewusst KEINE Regel und werden normal gelesen;
    # englisch "Atoms" matcht per Wortgrenze nicht und bleibt unberuehrt.
    "Atom": "Atom",
    "Atome": "Atome",
    "Atomkern": "Atomkern",
    "Elementarteilchen": "E-le-men-TAR-teil-chen",
    "Kraftfeld": "KRAFT-feld",
    "Magnetfeld": "Ma-gnet-FELD",
    "Elektrizität": "E-lek-tri-tsi-TÄT",
    "Spannung": "SPANN-ung",
    "Stromstärke": "STROM-stär-ke",
    "Widerstand": "Wi-der-STAND",
    "Leiter": "LEI-ter",
    "Isolator": "I-so-LA-tor",
    "Temperatur": "Tem-pe-ra-TUR",
    "Druck": "DRUCK",
    "Volumen": "Vo-LU-men",
    "Masse": "MAS-se",
    "Beschleunigung": "Be-schleu-ni-gung",
    "Geschwindigkeit": "Ge-schwin-dig-keit",
    "Impuls": "Im-PULS",
    "Drehimpuls": "Dreh-im-PULS",
    "Kinematik": "Ki-ne-MA-tik",
    "Dynamik": "Dy-NA-mik",
    "Statik": "STA-tik",
    "Optik": "OP-tik",
    "optisch": "OP-tisch",
    "Akustik": "A-KUS-tik",
    "akustisch": "a-KUS-tisch",
    "Spektrum": "SPEK-trum",
    "Spektren": "SPEK-tren",
    "Wellenlänge": "WEL-len-län-ge",
    "Amplitude": "Am-pli-TU-de",
    "Schwingung": "SCHWIN-gung",
    "Schwingungen": "SCHWIN-gun-gen",
    # --- Informatik / KI ---------------------------------------------------
    "Informatik": "In-for-MA-tik",
    "Informatiker": "In-for-MA-ti-ker",
    "informatisch": "in-for-MA-tisch",
    "künstliche Intelligenz": "KÜNST-li-che In-te-li-GENZ",
    "Künstliche Intelligenz": "KÜNST-li-che In-te-li-GENZ",
    "Künstlicher Intelligenz": "KÜNST-li-cher In-te-li-GENZ",
    "Machine Learning": "Mä-SCHIEN Lör-ning",
    "Deep Learning": "Dip Lör-ning",
    "Neural Network": "NJU-ral Netz-werk",
    "Neuronales Netz": "Neuro-NA-les Netz",
    "Transformer": "Trans-FOR-mer",
    "Transformermodell": "Trans-for-mer-mo-DELL",
    "Token": "TO-ken",
    "Tokens": "TO-kens",
    "Tokenisierung": "To-ke-ni-SIE-rung",
    "Prompt": "PROMT",
    "Prompts": "PROMTS",
    "Prompting": "PROMP-ting",
    "Embedding": "ÄM-bedding",
    "Embeddings": "ÄM-bed-dings",
    "Inferenz": "In-fe-RENZ",
    "Modell": "Mo-DELL",
    "Modelle": "Mo-DEL-le",
    "Modellierung": "Mo-del-LIE-rung",
    "GPU": "G P U",
    "CPU": "C P U",
    "TPU": "T P U",
    "CUDA": "KUH-da",
    "Python": "PEI-ton",
    "Software": "SORFT-wär",
    "Hardware": "HARD-wär",
    "Firmware": "FIRM-wär",
    "Middleware": "MID-del-wär",
    "Betriebssystem": "Be-TRIEBS-sys-tem",
    "Programmiersprache": "Pro-gram-MIER-spra-che",
    "Quellcode": "Quellcode",
    "Algorithmus": "Algorithmus",
    "Algorithmen": "Algorithmen",
    "Datenbank": "Datenbank",
    "Datenbanken": "Datenbanken",
    "Datenverarbeitung": "Datenverarbeitung",
    "Rechenleistung": "RE-chen-leis-tung",
    "Mikroprozessor": "Mi-kro-pro-TS-ess-sor",
    "Prozessor": "Prozessor",
    "Mikrochip": "MI-kro-tschip",
    "Parallelisierung": "Pa-ral-le-li-SIE-rung",
    "Vektorisierung": "Vek-to-ri-SIE-rung",
    "KI": "K I",
    "K. I.": "K I",
    "K.I.": "K I",
    "Artificial Intelligence": "Ar-ti-fi-schel In-te-li-DSCHENZ",
    "Artificial-Intelligence": "Ar-ti-fi-schel In-te-li-DSCHENZ",
    "Informationstheorie": "In-for-ma-tions-teo-RIE",
    "Informationstechnologie": "In-for-ma-tsi-ons-tech-no-lo-GIE",
    # Zusätzliche Tech-/Informatik-Begriffe (Systematik-Erweiterung) -----
    "Server": "SER-wer",
    "Client": "KLEI-ent",
    "Daten": "Daten",
    "Datensatz": "Datensatz",
    "Datensätze": "Datensätze",
    "Algorithmisierung": "Al-go-rith-mi-SIE-rung",
    "Kompilierung": "Kom-pi-LIE-rung",
    "Kompilieren": "Kom-pi-LIE-ren",
    "Frame": "Freim",
    "Framework": "Freim-wörk",
    "Library": "Lei-bre-ri",
    "Repository": "Re-po-si-to-ri",
    "Open Source": "O-pen Sors",
    "Open-Source": "O-pen-Sors",
    "Kern": "KERN",
    "Kernel": "KER-nel",
    "Datenbank": "Datenbank",
    "Datenbanken": "Datenbanken",
    "Netzwerk": "NETZ-werk",
    "Netzwerke": "NETZ-wer-ke",
    # --- Technik / Ingenieur ----------------------------------------------
    "Ingenieur": "In-ge-NIÖR",
    "Ingenieure": "In-ge-ni-Ö-re",
    "Technik": "TECH-nik",
    "Techniker": "TECH-ni-ker",
    "technisch": "TECH-nisch",
    "Technologie": "Tech-no-lo-GIE",
    "technologisch": "tech-no-LO-gisch",
    "Elektrotechnik": "E-lek-tro-TECH-nik",
    "Maschinenbau": "Ma-SCHI-nen-bau",
    "Bauingenieur": "Bau-in-ge-ni-ÖR",
    "Werkstoffkunde": "WERK-stoff-kun-de",
    "Regelungstechnik": "RE-ge-lungs-technik",
    "Nachrichtentechnik": "NACH-rich-ten-tech-nik",
    "Mikroelektronik": "Mi-kro-e-lek-TRO-nik",
    "Halbleiter": "HALB-lei-ter",
    "Transistor": "Trans-IS-tor",
    "Transistoren": "Trans-is-TO-ren",
    "Widerstand": "Wi-der-STAND",
    "Kondensator": "Kon-den-SA-tor",
    "Diode": "di-O-de",
    # --- Medizin / Biologie ------------------------------------------------
    "Neurowissenschaft": "Neurowissenschaft",
    "Neurowissenschaften": "Neu-ro-WIS-sen-schaf-ten",
    "Bewusstseinsforschung": "Be-WUSST-seins-for-schung",
    "Gehirnforschung": "Ge-HIRN-for-schung",
    "Neurotransmitter": "Neu-ro-trans-MIT-ter",
    "Neuroplastizität": "Neu-ro-plas-ti-ZI-tät",
    "Genetik": "Ge-ne-TIK",
    "genetisch": "ge-NE-tisch",
    "DNS": "D N S",
    "RNS": "R N S",
    "DNA": "D N A",
    "RNA": "R N A",
    # Identity-Mappings (bewusst, Muster wie Mathematik/Bewusstsein):
    # "TSEL-le"/"TSEL-len" sind kuenstliche Silben-Respells (Bindestrich +
    # GROSS-Cluster) und fuehrten im echten Qwen-Pfad zu falscher
    # Aussprache (Nutzer-Hoerbefund). NATUERLICHE Orthographie;
    # Zell-Komposita haben bewusst keine Regel (Corpus relevanz: keine).
    "Zelle": "Zelle",
    "Zellen": "Zellen",
    "Organismus": "Or-ga-NIS-mus",
    # --- Weitere Wissenschaften --------------------------------------------
    "Astronomie": "A-stro-no-MIE",
    "astronomisch": "a-stro-NO-misch",
    "Geologie": "Ge-o-lo-GIE",
    "Soziologie": "Zo-tsi-o-lo-GIE",
    "Soziologe": "Zo-tsi-o-LO-ge",
    "Ökonomie": "Ö-ko-NO-mie",
    "ökonomisch": "ö-ko-NO-misch",
    "Philosophie": "fi-lo-zo-FIE",
    "Philosoph": "FI-lo-sof",
    "Philosophen": "fi-lo-ZO-fen",
    "philosophisch": "fi-lo-ZO-fisch",
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

# Sichere Suffix-Regeln für deutsche Komposita (generisch, nicht wort-spezifisch)
# – …theorie -> …-teo-RIE  sowie zusätzlich …wissenschaft, …geist, …logie etc.
# Alle Regeln TTS-intern, nur für lange Komposita, kuratierte exakte Einträge gewinnen immer.
_THEORIE_SUFFIX = re.compile(r"([A-Za-zäöüß-]+)theorie\b")
_THEORETISCH = re.compile(r"\btheoretisch\b")
_WISSENSCHAFT_SUFFIX = re.compile(r"([A-Za-zäöüß-]{3,})wissenschaft\b")
_GEIST_SUFFIX = re.compile(r"([A-Za-zäöüß-]{2,})geist\b")
_LOGIE_SUFFIX = re.compile(r"([A-Za-zäöüß-]{4,})logie\b")
_SCHAFT_SUFFIX = re.compile(r"([A-Za-zäöüß-]{5,})schaft\b")

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

    def _factory(repl: str, full: str, rule_id: str = "DE_TECH_term"):
        def _r(m: re.Match) -> str:
            out = m.group(0)
            before = full[max(0, m.start() - 2):m.start()]
            at_start = m.start() == 0 or before.rstrip().endswith(
                (".", "!", "?", ":", ";", "\n"))
            repl_c = repl[0].upper() + repl[1:] if at_start else repl
            replacements.append({"from": out, "to": repl_c,
                                 "rule": rule_id})
            return repl_c
        return _r

    for term in sorted(mapping, key=len, reverse=True):
        if term in _KEEP:
            continue
        # Boundary: kein Buchstabe/Umlaut/Bindestrich direkt davor/dahinter
        # (Bindestrich erlaubt, damit Begriffe in Komposita wie
        # „Business-Mindset-Coaching“ erfasst werden – Bindestrich ist im
        # Deutschen ein legitimer Komposita-Trenner). Akronyme wie „USB“
        # werden bereits in normalize_text zu „U S B“ buchstabiert und
        # sind dann keine Match-Kandidaten mehr für die Tech-Map.
        # Bindestrich als Grenze erlauben, damit Begriffe in
        # Bindestrich-Komposita (z.B. „Business-Mindset-Coaching“)
        # erfasst werden – der Lookahead erlaubt einen folgenden
        # Bindestrich (der selbst kein Wortzeichen ist).
        pattern = re.compile(r"(?<![\wÄÖÜäöüß])" + re.escape(term) +
                             r"(?=$|[\-.,;:!?)\]\s]|$)", re.IGNORECASE)
        if pattern.search(text):
            text = pattern.sub(_factory(mapping[term], text,
                                        f"DE_TECH_{term}"), text)

    # generische Komposita auf „…theorie“ (nicht kuratiert, >= 8 Zeichen)
    def _comp(m: re.Match) -> str:
        stem = m.group(1)
        if stem[-1] not in "nsvtsr":
            stem = stem + "s" if stem[-1] not in "s" else stem
        repl = f"{stem}-teo-RIE"
        replacements.append({"from": m.group(0), "to": repl,
                             "rule": "DE_TECH_suffix_theorie"})
        return repl
    # KASKADEN-GUARD (Muster der …wissenschaft-Regel): kuratierte Eintraege
    # (inkl. Identity-Mappings wie "Erkenntnistheorie") duerfen von der
    # Suffixregel NICHT nachtraeglich ueberschrieben werden – Identity
    # laesst den Originaltext intakt, ohne Guard griffe die Suffixregel
    # erneut (Befund 2026-09: "Erkenntnistheorie" -> "Erkenntnis-teo-RIE").
    text = _THEORIE_SUFFIX.sub(
        lambda m: _comp(m) if m.group(0) not in mapping else m.group(0),
        text)

    # generische Komposita auf „…wissenschaft“ (lang, z. B. Kognitionswissenschaft)
    # Beispiel: „Kognitionswissenschaft“ → „Kognitions-wis-sen-schaft“ – nur wenn nicht kuratiert
    def _wiss(m: re.Match) -> str:
        stem = m.group(1)
        # Stamm sauber halten, Bindestrich für TTS-Betonung
        repl = f"{stem}-wis-sen-schaft"
        replacements.append({"from": m.group(0), "to": repl,
                             "rule": "DE_TECH_suffix_wissenschaft"})
        return repl
    # Nur bei Wörtern >= 13 Zeichen (inkl. Suffix), um kurze Fehlmatches zu vermeiden
    text = _WISSENSCHAFT_SUFFIX.sub(lambda m: _wiss(m) if len(m.group(0)) >= 13 and m.group(0) not in mapping else m.group(0), text)

    # generische Komposita auf „…geist“ (z. B. Erdgeist → Erd-geist, Zeitgeist → Zeit-geist)
    # Hilft bei Übergang „Erdgeist + Folgewort“ durch klare Silbenmarkierung
    def _geist(m: re.Match) -> str:
        stem = m.group(1)
        repl = f"{stem}-geist"
        replacements.append({"from": m.group(0), "to": repl,
                             "rule": "DE_TECH_suffix_geist"})
        return repl
    # Nur bei unbekannten Komposita (kuratierte wie Erdgeist selbst nicht in TECH_TERMS, also greift Suffix)
    # Schützt kurze Kernwörter „Geist“ allein nicht
    text = _GEIST_SUFFIX.sub(lambda m: _geist(m) if len(m.group(0)) >= 7 and m.group(1) else m.group(0), text)

    # generische Komposita auf „…logie“ (Phy → …-lo-GIE) – sanft, nur Stamm >=4
    def _logie(m: re.Match) -> str:
        stem = m.group(1)
        repl = f"{stem}-lo-GIE"
        replacements.append({"from": m.group(0), "to": repl,
                             "rule": "DE_TECH_suffix_logie"})
        return repl
    # Nur wenn nicht kuratiert (TECH_TERMS deckt Psychologie etc. bereits ab)
    text = _LOGIE_SUFFIX.sub(lambda m: _logie(m) if m.group(0) not in mapping else m.group(0), text)

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
