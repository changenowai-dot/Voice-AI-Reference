"""Eigennamen-Erkennung für deutsche Texte (Phase 1, Anforderung 10).

Erkennt Personen, Orte, Firmen, Marken, historische, wissenschaftliche
und mythologische Namen. Liefert Typ + Risikoeinschätzung (falsche
Aussprache wahrscheinlich?) und arbeitet mit dem Aussprache-Wörterbuch
zusammen: Bekannte problematische Namen bekommen eine Empfehlung,
unbekannte werden intern gekennzeichnet (flagged), statt dass eine
willkürliche Aussprache erzwungen wird.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Kuratierte Gazetteers (deutschsprachiger Kontext, ~150 Einträge)
# risk=True: Schreibung weicht von deutschen Lesegewohnheiten ab
# ---------------------------------------------------------------------------
PERSONS: dict[str, dict] = {
    # Philosophie / Psychologie
    "Nietzsche": {"type": "Philosoph", "risk": False},
    "Kierkegaard": {"type": "Philosoph", "risk": True},
    "Søren": {"type": "Vorname", "risk": True},
    "Kant": {"type": "Philosoph", "risk": False},
    "Hegel": {"type": "Philosoph", "risk": True},
    "Heidegger": {"type": "Philosoph", "risk": True},
    "Wittgenstein": {"type": "Philosoph", "risk": False},
    "Schopenhauer": {"type": "Philosoph", "risk": False},
    "Freud": {"type": "Psychologe", "risk": False},
    "Jung": {"type": "Psychologe", "risk": False},
    "Adler": {"type": "Psychologe", "risk": False},
    "Adorno": {"type": "Philosoph", "risk": True},
    "Horkheimer": {"type": "Philosoph", "risk": False},
    "Marcuse": {"type": "Philosoph", "risk": True},
    "Foucault": {"type": "Philosoph", "risk": True},
    "Deleuze": {"type": "Philosoph", "risk": True},
    "Derrida": {"type": "Philosoph", "risk": True},
    "Sartre": {"type": "Philosoph", "risk": True},
    "Camus": {"type": "Philosoph", "risk": True},
    "Beauvoir": {"type": "Philosophin", "risk": True},
    "Descartes": {"type": "Philosoph", "risk": True},
    "Voltaire": {"type": "Philosoph", "risk": True},
    "Rousseau": {"type": "Philosoph", "risk": True},
    "Montaigne": {"type": "Philosoph", "risk": True},
    "Platon": {"type": "Philosoph", "risk": False},
    "Aristoteles": {"type": "Philosoph", "risk": False},
    "Sokrates": {"type": "Philosoph", "risk": False},
    "Seneca": {"type": "Philosoph", "risk": False},
    "Epiktet": {"type": "Philosoph", "risk": False},
    "Aurelius": {"type": "Philosoph", "risk": False},
    "Konfuzius": {"type": "Philosoph", "risk": False},
    "Laotse": {"type": "Philosoph", "risk": False},
    # Wissenschaft
    "Einstein": {"type": "Physiker", "risk": True},
    "Heisenberg": {"type": "Physiker", "risk": True},
    "Schrödinger": {"type": "Physiker", "risk": False},
    "Planck": {"type": "Physiker", "risk": False},
    "Hawking": {"type": "Physiker", "risk": True},
    "Stephen": {"type": "Vorname", "risk": True},
    "Darwin": {"type": "Biologe", "risk": False},
    "Mendel": {"type": "Biologe", "risk": False},
    "Kopernikus": {"type": "Astronom", "risk": False},
    "Kepler": {"type": "Astronom", "risk": False},
    "Galilei": {"type": "Astronom", "risk": False},
    "Newton": {"type": "Physiker", "risk": False},
    "Turing": {"type": "Mathematiker", "risk": False},
    "Gödel": {"type": "Mathematiker", "risk": False},
    "Röntgen": {"type": "Physiker", "risk": False},
    "Koch": {"type": "Mediziner", "risk": False},
    "Pasteur": {"type": "Chemiker", "risk": True},
    "Curie": {"type": "Physikerin", "risk": True},
    "Marie": {"type": "Vorname", "risk": False},
    # Literatur
    "Goethe": {"type": "Dichter", "risk": True},
    "Schiller": {"type": "Dichter", "risk": False},
    "Kafka": {"type": "Autor", "risk": False},
    "Rilke": {"type": "Dichter", "risk": False},
    "Brecht": {"type": "Dichter", "risk": False},
    "Mann": {"type": "Autor", "risk": False},
    "Dostojewski": {"type": "Autor", "risk": False},
    "Tolstoi": {"type": "Autor", "risk": False},
    "Proust": {"type": "Autor", "risk": True},
    "Céline": {"type": "Autor", "risk": True},
    "Shakespeare": {"type": "Dichter", "risk": True},
    "Orwell": {"type": "Autor", "risk": False},
    "Hesse": {"type": "Autor", "risk": False},
    "Borges": {"type": "Autor", "risk": True},
    # Geschichte / Politik
    "Bismarck": {"type": "Politiker", "risk": False},
    "Adenauer": {"type": "Politiker", "risk": False},
    "Churchill": {"type": "Politiker", "risk": True},
    "Roosevelt": {"type": "Politiker", "risk": True},
    "Kennedy": {"type": "Politiker", "risk": False},
    "Gorbatschow": {"type": "Politiker", "risk": False},
    "Charlemagne": {"type": "Herrscher", "risk": True},
    "Napoleon": {"type": "Herrscher", "risk": False},
    "Cäsar": {"type": "Herrscher", "risk": False},
    "Attila": {"type": "Herrscher", "risk": False},
    "Dschingis": {"type": "Herrscher", "risk": True},
    # Gegenwart / Tech
    "Musk": {"type": "Unternehmer", "risk": False},
    "Bezos": {"type": "Unternehmer", "risk": True},
    "Zuckerberg": {"type": "Unternehmer", "risk": False},
    "Altman": {"type": "Unternehmer", "risk": False},
    "Hinton": {"type": "Forscher", "risk": False},
    "LeCun": {"type": "Forscher", "risk": True},
}

PLACES: dict[str, dict] = {
    "Göbekli Tepe": {"type": "Ausgrabungsstätte", "risk": True},
    "Şanlıurfa": {"type": "Stadt", "risk": True},
    "Machu Picchu": {"type": "Stätte", "risk": True},
    "Stonehenge": {"type": "Stätte", "risk": True},
    "Pompeji": {"type": "Stadt", "risk": False},
    "Edinburgh": {"type": "Stadt", "risk": True},
    "Thames": {"type": "Fluss", "risk": True},
    "Los Angeles": {"type": "Stadt", "risk": True},
    "New Orleans": {"type": "Stadt", "risk": True},
    "Quebec": {"type": "Stadt", "risk": True},
    "Montréal": {"type": "Stadt", "risk": False},
    "Wien": {"type": "Stadt", "risk": False},
    "München": {"type": "Stadt", "risk": False},
    "Köln": {"type": "Stadt", "risk": False},
    "Zürich": {"type": "Stadt", "risk": False},
    "Praha": {"type": "Stadt", "risk": False},
    "Reichstag": {"type": "Gebäude", "risk": False},
    "Neuschwanstein": {"type": "Schloss", "risk": False},
    "Tschernobyl": {"type": "Stadt", "risk": False},
    "Hiroshima": {"type": "Stadt", "risk": True},
    "Nagasaki": {"type": "Stadt", "risk": False},
    "Auschwitz": {"type": "Gedenkstätte", "risk": False},
    "Sarajevo": {"type": "Stadt", "risk": False},
    "Kiew": {"type": "Stadt", "risk": False},
    "Babylon": {"type": "Stadt", "risk": False},
    "Alexandria": {"type": "Stadt", "risk": False},
    "Konstantinopel": {"type": "Stadt", "risk": False},
}

BRANDS: dict[str, dict] = {
    "NVIDIA": {"type": "Marke", "risk": True},
    "ChatGPT": {"type": "Produkt", "risk": True},
    "OpenAI": {"type": "Firma", "risk": True},
    "Google": {"type": "Firma", "risk": True},
    "YouTube": {"type": "Plattform", "risk": True},
    "Facebook": {"type": "Plattform", "risk": False},
    "Instagram": {"type": "Plattform", "risk": False},
    "TikTok": {"type": "Plattform", "risk": False},
    "Spotify": {"type": "Dienst", "risk": True},
    "Netflix": {"type": "Firma", "risk": False},
    "Reddit": {"type": "Plattform", "risk": True},
    "Wikipedia": {"type": "Plattform", "risk": False},
    "Amazon": {"type": "Firma", "risk": True},
    "Microsoft": {"type": "Firma", "risk": False},
    "Apple": {"type": "Firma", "risk": False},
    "iPhone": {"type": "Produkt", "risk": True},
    "SpaceX": {"type": "Firma", "risk": True},
    "Tesla": {"type": "Firma", "risk": False},
    "Patreon": {"type": "Dienst", "risk": True},
    "Discord": {"type": "Dienst", "risk": False},
    "GitHub": {"type": "Dienst", "risk": True},
    "Bluesky": {"type": "Plattform", "risk": False},
    "Substack": {"type": "Dienst", "risk": False},
    "PayPal": {"type": "Dienst", "risk": True},
    "ASML": {"type": "Firma", "risk": True},
    "CERN": {"type": "Forschung", "risk": False},
    "NASA": {"type": "Behörde", "risk": False},
}

MYTHOLOGY: dict[str, dict] = {
    "Odysseus": {"type": "mythologisch", "risk": False},
    "Prometheus": {"type": "mythologisch", "risk": False},
    "Ikarus": {"type": "mythologisch", "risk": False},
    "Narziss": {"type": "mythologisch", "risk": False},
    "Ödipus": {"type": "mythologisch", "risk": False},
    "Sisyphos": {"type": "mythologisch", "risk": True},
    "Orpheus": {"type": "mythologisch", "risk": True},
    "Eurydike": {"type": "mythologisch", "risk": True},
    "Achilles": {"type": "mythologisch", "risk": True},
    "Kassandra": {"type": "mythologisch", "risk": False},
    "Medusa": {"type": "mythologisch", "risk": False},
    "Sphinx": {"type": "mythologisch", "risk": False},
    "Minotaurus": {"type": "mythologisch", "risk": False},
    "Titanen": {"type": "mythologisch", "risk": False},
    "Valhalla": {"type": "mythologisch", "risk": True},
    "Ragnarök": {"type": "mythologisch", "risk": True},
    "Nirwana": {"type": "religiös", "risk": False},
    "Karma": {"type": "religiös", "risk": False},
}

SCIENTIFIC: dict[str, dict] = {
    "Amygdala": {"type": "Anatomie", "risk": True},
    "Cortisol": {"type": "Biochemie", "risk": False},
    "Dopamin": {"type": "Biochemie", "risk": False},
    "Serotonin": {"type": "Biochemie", "risk": False},
    "Präfrontalkortex": {"type": "Anatomie", "risk": False},
    "Hippocampus": {"type": "Anatomie", "risk": False},
    "Neurotransmitter": {"type": "Fachbegriff", "risk": False},
    "Kognition": {"type": "Fachbegriff", "risk": False},
    "Dissonanz": {"type": "Fachbegriff", "risk": False},
    "Entropie": {"type": "Physik", "risk": False},
    "Quantenverschränkung": {"type": "Physik", "risk": False},
    "Relativitätstheorie": {"type": "Physik", "risk": False},
    "Placebo": {"type": "Medizin", "risk": True},
    "Nocebo": {"type": "Medizin", "risk": True},
    "Limbisches System": {"type": "Anatomie", "risk": False},
}

# Phase 2 (§13): Hermetik/Kybalion + Systemtheorie/Neurowissenschaft
HERMETIC: dict[str, dict] = {
    "Kybalion": {"type": "Werk", "risk": True},
    "Hermes Trismegistos": {"type": "mythologisch", "risk": True},
    "Trismegistos": {"type": "mythologisch", "risk": True},
    "Thoth": {"type": "mythologisch", "risk": True},
    "Gnosis": {"type": "religiös", "risk": False},
    "Kabbala": {"type": "religiös", "risk": True},
    "Smaragdtafel": {"type": "Werk", "risk": True},
    "Paracelsus": {"type": "Arzt/Alchemist", "risk": True},
    "Ficino": {"type": "Philosoph", "risk": True},
    "Giordano Bruno": {"type": "Philosoph", "risk": True},
    "Jakob Böhme": {"type": "Mystiker", "risk": False},
    "Blavatsky": {"type": "Okkultistin", "risk": True},
    "William Walker Atkinson": {"type": "Autor", "risk": True},
    "Ramacharaka": {"type": "Pseudonym", "risk": True},
}

SYSTEM_SCIENCE: dict[str, dict] = {
    "Systemtheorie": {"type": "Fachgebiet", "risk": False},
    "Neurowissenschaft": {"type": "Fachgebiet", "risk": False},
    "Autopoiesis": {"type": "Fachbegriff", "risk": True},
    "Homöostase": {"type": "Fachbegriff", "risk": True},
    "Kybernetik": {"type": "Fachgebiet", "risk": False},
    "Luhmann": {"type": "Soziologe", "risk": False},
    "Bateson": {"type": "Forscher", "risk": True},
    "von Foerster": {"type": "Forscher", "risk": True},
    "Prigogine": {"type": "Physiker", "risk": True},
    "Neuroplastizität": {"type": "Fachbegriff", "risk": False},
    "Emergenz": {"type": "Fachbegriff", "risk": False},
}

_GAZETTEERS = [("Person", PERSONS), ("Ort", PLACES), ("Marke", BRANDS),
               ("Mythologie", MYTHOLOGY), ("Wissenschaft", SCIENTIFIC),
               ("Hermetik", HERMETIC), ("Systemwissenschaft", SYSTEM_SCIENCE)]

# Lookup: Name -> (Kategorie-Typ, risk)
KNOWN_NAMES: dict[str, tuple[str, bool]] = {}
for _cat, _gaz in _GAZETTEERS:
    for _name, _info in _gaz.items():
        KNOWN_NAMES[_name] = (_info["type"], _info["risk"])

# Wörter, die zwar großgeschrieben sind, aber keine Eigennamen sind
_NOT_NAMES = re.compile(
    r"^(?:Ich|Du|Er|Sie|Es|Wir|Ihr|Der|Die|Das|Den|Dem|Des|Ein|Eine|Einen|"
    r"Einem|Einer|Im|In|An|Am|Auf|Für|Von|Mit|Zu|Zum|Zur|Beim|Nach|Über|"
    r"Unter|Vor|Hinter|Neben|Zwischen|Durch|Gegen|Ohne|Um|Und|Oder|Aber|"
    r"Denn|Weil|Dass|Wenn|Als|Wie|So|Doch|Ja|Nein|Nicht|Kein|Mehr|Nur|"
    r"Schon|Auch|Noch|Immer|Wieder|Dann|Jetzt|Hier|Dort|Was|Wer|Wo|Wann|"
    r"Warum|Weshalb|Deshalb|Deswegen|Außerdem|Zunächst|Während|Später|"
    r"Kapitel|Teil|Abschnitt|Januar|Februar|März|April|Mai|Juni|Juli|"
    r"August|September|Oktober|November|Dezember|Montag|Dienstag|Mittwoch|"
    r"Donnerstag|Freitag|Samstag|Sonntag)$")


@dataclass
class NameMention:
    name: str
    category: str          # Person | Ort | Marke | Mythologie | Wissenschaft | Unbekannt
    detail: str = ""
    risk: bool = False     # Aussprache wahrscheinlich problematisch
    covered: bool = False  # im Aussprache-Wörterbuch vorhanden
    context: str = ""      # umgebende Wörter (Datenschutz: kurz)


def scan_names(text: str, dictionary_terms: set[str] | None = None,
               max_mentions: int = 60) -> list[NameMention]:
    """Findet Eigennamen-Vorkommen im Text.

    dictionary_terms: Schlüssel des aktiven Aussprache-Wörterbuchs
    (für coverage). Liefert_FLAGGED Stellen statt Aussprachen zu raten.
    """
    dict_terms = {t.lower() for t in (dictionary_terms or set())}
    mentions: list[NameMention] = []
    # 1) Bekannte Gazetteer-Namen (auch mehrwortig, längste zuerst)
    for name in sorted(KNOWN_NAMES, key=len, reverse=True):
        for m in re.finditer(r"(?<![\wÄÖÜäöüß])" + re.escape(name) +
                             r"(?![\wÄÖÜäöüß])", text):
            cat, risk = KNOWN_NAMES[name]
            covered = name.lower() in dict_terms
            mentions.append(NameMention(
                name=name, category=cat, detail="", risk=risk,
                covered=covered,
                context=_short_context(text, m.start(), m.end())))
    # 2) Heuristik: weitere großgeschriebene Wörter (nicht Satzanfang,
    #    nicht Stopwort, nicht schon erfasst)
    taken_spans = [(text.find(mm.name), text.find(mm.name) + len(mm.name))
                   for mm in mentions]
    for m in re.finditer(r"(?<![\wÄÖÜäöüß.-])([A-ZÄÖÜ][a-zäöüß]{3,})"
                         r"(?![\wÄÖÜäöüß])", text):
        w = m.group(1)
        if _NOT_NAMES.match(w):
            continue
        s, e = m.start(), m.end()
        if any(s < te and ts < e for ts, te in taken_spans):
            continue
        # Mehrfachvorkommen zählen -> wahrscheinlich Eigenname
        occurrences = len(re.findall(r"(?<![\wÄÖÜäöüß])" + re.escape(w) +
                                     r"(?![\wÄÖÜäöüß])", text))
        unusual = not _looks_german(w)
        mentions.append(NameMention(
            name=w, category="Unbekannt",
            risk=(unusual or occurrences >= 3),
            covered=w.lower() in dict_terms,
            context=_short_context(text, s, e)))
    return mentions[:max_mentions]


def _short_context(text: str, s: int, e: int, pad: int = 18) -> str:
    left = text[max(0, s - pad):s].strip()
    right = text[e:e + pad].strip()
    return f"…{left} [{text[s:e]}] {right}…".replace("\n", " ")


def _looks_german(word: str) -> bool:
    """Heuristik: wirkt das Wort deutsch ausgesprochen?"""
    w = word.lower()
    if len(w) >= 5:
        common = re.search(r"(sch|tz|tzs|chs|ei|ie|eu|äu|ü|ö|ß|ck|ling|"
                           r"ung|keit|heit|schaft|tum|nis|lich|isch)", w)
        unusual = re.search(r"(th|ph|ough|augh|wh\w|ee|oo|qu|sh\b)", w)
        if common and not unusual:
            return True
        if unusual and not common:
            return False
    else:
        common = re.search(r"(sch|tz|ei|ie|eu|äu|ü|ö|ß|ck)", w)
    return bool(common)


def risky_unknown_names(mentions: list[NameMention]) -> list[NameMention]:
    """Problematische, UNBEDECKTE Namen -> für Bericht/Wörterbuch-Workflow."""
    return [m for m in mentions if m.risk and not m.covered]
