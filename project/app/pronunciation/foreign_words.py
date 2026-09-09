"""Kontextabhängige Fremdwort-Behandlung für deutsche Texte (Anf. 11).

Regeln:
- Ein deutsches TTS-System darf nicht pauschal jedes englische Wort
  englisch aussprechen – und umgekehrt.
- Anglizismen im deutschen Satz („Meeting“, „Deadline“) bekommen die
  eingebürgerte deutsch-assimilierte Realisierung (Respwelling).
- Echte englische Phrasen/Zitate (>=3 aufeinanderfolgende englische
  Wörter oder in Anführungszeichen) werden dem Modell überlassen
  (cross-lingual), ohne Eingriff.
- Vollständig absorbierte Lehnwörter („Computer“, „Internet“) bleiben
  unangetastet – Qwen3-TTS spricht sie mit language=German deutsch.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Eingebürgerte Anglizismen -> deutsch-assimilierte Aussprache
# (nur Wörter, die von TTS-Systemen häufig anglisiert/verhunzt werden)
LOANWORDS_DE: dict[str, str] = {
    "Meeting": "Mieting", "Meetings": "Mietings",
    "Deadline": "Dedlein", "Deadlines": "Dedleins",
    "Feedback": "Fidbek",
    "Management": "Mänidschment",
    "Challenge": "Tschällendsch", "Challenges": "Tschällendsches",
    "Story": "Stori", "Stories": "Storis",
    "Team": "Tiem", "Teams": "Tiems",
    "Job": "Dschobb", "Jobs": "Dschobbs",
    "Teenager": "Tinäidscher",
    "Baby": "Behbi", "Babys": "Behbis",
    "Happy": "Häppi",
    "Cool": "kuhl",
    "Design": "Disain", "Designer": "Disainer",
    "Lifestyle": "Leifstail",
    "Marketing": "Märketing",
    "Content": "Kontent",
    "Follower": "Folloer", "Followers": "Folloer",
    "Community": "Kommjunitti",
    "Interview": "Interwju", "Interviews": "Interwjus",
    "Movie": "Muwi", "Movies": "Muwis",
    "Trailer": "Treiler",
    "Plot": "Plott",
    "Fake": "Feik",
    "News": "Njuhs",
    "Bullying": "Bullaising",
    "Burnout": "Bernaut",
    "Coaching": "Koutsching",
    "Browser": "Brauser",
    "Downlo­ad": "Daunloud",   # Schutz vor Soft-Hyphen irrelevant
    "Download": "Daunloud", "Downloads": "Daunlouds",
    "Upload": "Aplaud",
    "Update": "Apdeit", "Updates": "Apdeits",
    "Podcast": "Podkast", "Podcasts": "Podkasts",
    "Creator": "Krieitor", "Creators": "Kreitoren",
    "Feature": "Fitscher",
    "Highlight": "Halait",
    "Timeline": "Teimlain",
    "Livestream": "Laifstrim",
    "Statement": "Steitment", "Statements": "Steitments",
    "Eyecatcher": "Aikätscher",
    "Bestseller": "Bestseller",
    "Talkshow": "Tokschou", "Show": "Schou", "Shows": "Schous",
    # Psychologie-/Fachenglisch in deutschen Texten (explizit gewünscht)
    "Psychology": "Saikolodzi",
    "Mindset": "Meindset", "Mindsets": "Meindsets",
    "Deep Learning": "Dip Lörning",
    "Attachment": "Etätschment",
    "Behavior": "Bihejwer", "Behavioral": "Bihejwörel",
    "Insight": "Insait", "Insights": "Insaits",
    "Awareness": "Ehwärniss",
    "Coping": "Kouping",
    "Counselling": "Kaunsäling", "Counseling": "Kaunsäling",
    "Mindfulness": "Meindfuhlniss",
    "Trial": "Treil",
    "Stimulus": "Stimulus", "Stimuli": "Stimulai",
}

# Vollständig absorbiert – KEINE Ersetzung nötig (Dokumentation)
ABSORBED = {
    "Computer", "Internet", "Email", "E-Mail", "Software", "Hardware",
    "Server", "Designer", "Manager", "Training", "Stress", "Mobbing",
    "Test", "Trend", "Center", "Party", "Sport", "Song", "Film",
    "Krimi", "Thriller", "Horror", "Western", "Tempo", "Super",
}

_EN_WORD = re.compile(r"[A-Za-z]+")

# Deutsche Kernliste (Funktionswörter + häufigste Wörter) für die
# Erkennung echter englischer Phrasen
_DE_CORE = set("""
der die das den dem des ein eine einen einem einer eines und oder nicht
ist sind war waren sei seid wird werden wurde wurden hat habe haben hatte
hatten kann könnte muss muss sollen will wollen soll wollte darf möchte
im in an auf für von mit zu zum zur beim nach über unter vor hinter neben
zwischen durch gegen ohne um als wie so doch ja nein kein keine keinen
mehr immer wieder dann jetzt hier dort was wer wo wann warum weshalb
deshalb deswegen außerdem zunächst während später endlich schluss
man auch noch nur schon sehr aber dass weil wenn ob bevor nachdem
ich du er sie es wir ihr mich dich ihn uns euch mir dir ihm ihnen
mein dein sein unser euer mein deine seine unsere eure
ganz ganze ganzen eigenen bestimmten einfach besonders verschiedenen
gleich wieder immer noch nie oft selten heute morgen gestern abend
jahr jahre jahren jahrhundert zeit zeiten welt mensch menschen
geschichte geschichten beispiel beispiele frage fragen antwort
antworten sutte sache sachen ding dinge ort orte stadt städte
land länder idee ideen gedanke gedanken gefühl gefühle sinn kraft
wichtig wichtige wichtigsten guten großen kleinen alten neuen
ersten zweiten dritten letzten beiden vielen wenigen allen
wurde gemacht gesagt geschrieben gesehen gekommen gegangen gegeben
gefunden genannt gesagt zeigt sagt spricht spricht
""".split())

_DE_SUFFIX = re.compile(
    r"(ung|heit|keit|schaft|lich|isch|bar|sam|halt|fältig|fähig|ung|"
    r"end(?:e|en|er|es)?|ern|em|er|en|st|te|ten|tet|test)$")


def _is_likely_german(word: str) -> bool:
    """Wort wirkt deutsch (Umlaute, Kernliste oder deutsche Endung)."""
    w = word.lower()
    if re.search(r"[äöüß]", w):
        return True
    if w in _DE_CORE:
        return True
    # typisch deutsche Ableitungen (nur bei Länge >= 6, um
    # englische „-er/-en"-Wörter nicht zu fälschlich als deutsch zu werten)
    if len(w) >= 6 and _DE_SUFFIX.search(w) and not re.search(
            r"(tion|sion|ity|ment|ness|able|ible)$", w):
        return True
    return False


@dataclass
class ForeignWordDecision:
    word: str
    action: str                 # "loanword_de" | "english_phrase" | "absorbed" | "leave"
    replacement: str | None = None
    reason: str = ""


def _is_english_run(text: str, start: int, end: int) -> bool:
    """>=3 aufeinanderfolgende englische Wörter -> echte Phrase."""
    left = text[:start]
    right = text[end:]
    # zähle englische Wörter unmittelbar davor/dahinter (grober Test:
    # Sequenz von ASCII-Wörtern ohne deutsche Marker)
    run = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", left[-40:] + "§" + right[:40])
    return False  # Platzhalter – echte Prüfung unten in analyze


def analyze_foreign_words(text: str, language: str = "German") -> list[ForeignWordDecision]:
    """Entscheidet für jedes fremdsprachig wirkende Wort im deutschen Text.

    Kriterien (Anforderung 11): Kontext, Sprache des Gesamttextes,
    Wort, bekannte Regeln, Ausspracheliste.
    """
    if not language.lower().startswith("ger"):
        return []
    decisions: list[ForeignWordDecision] = []
    # In Anführungszeichen stehende Passagen dem Modell überlassen
    quoted_spans = [(m.start(), m.end()) for m in re.finditer(
        r"[\"„»][^\"„«»]{2,90}[\"“«»]", text)]

    def _in_quotes(pos: int) -> bool:
        return any(s <= pos <= e for s, e in quoted_spans)

    single_keys = {k.lower(): k for k in LOANWORDS_DE if " " not in k}
    multi_keys = sorted((k for k in LOANWORDS_DE if " " in k),
                        key=len, reverse=True)

    # Mehrwort-Anglizismen zuerst („Deep Learning“)
    multi_hits: list[tuple[int, int, str, str]] = []
    for key in multi_keys:
        for m in re.finditer(r"(?<![\wÄÖÜäöüß'])" + re.escape(key) +
                             r"(?![\wÄÖÜäöüß'])", text, re.IGNORECASE):
            multi_hits.append((m.start(), m.end(), m.group(0),
                               LOANWORDS_DE[key]))
    multi_hits.sort()

    def _in_multi(pos: int, end: int) -> tuple[str, str] | None:
        for s, e, w, repl in multi_hits:
            if s <= pos and end <= e:
                return w, repl
        return None

    for m in re.finditer(r"(?<![\wÄÖÜäöüß'])([A-Za-z][A-Za-z'-]{2,})"
                         r"(?![\wÄÖÜäöüß'])", text):
        w = m.group(1)
        # eindeutig deutsche Wörter überspringen
        if re.search(r"[ÄÖÜäöüß]", w) or _is_likely_german(w):
            continue
        # Teil eines Mehrwort-Anglizismus?
        multi = _in_multi(m.start(), m.end())
        if multi:
            decisions.append(ForeignWordDecision(
                word=multi[0], action="loanword_de", replacement=multi[1],
                reason="Mehrwort-Anglizismus (deutsche Realisierung)"))
            continue
        run_len = _english_run_at(text, m.start(), m.end())
        if run_len >= 3 or _in_quotes(m.start()):
            decisions.append(ForeignWordDecision(
                word=w, action="english_phrase",
                reason=("zitierte englische Phrase" if _in_quotes(m.start())
                        else f"{run_len} englische Wörter in Folge")))
            continue
        key = single_keys.get(w.lower())
        if key:
            decisions.append(ForeignWordDecision(
                word=w, action="loanword_de",
                replacement=LOANWORDS_DE[key],
                reason="eingebürgerter Anglizismus (deutsche Realisierung)"))
        elif w in ABSORBED:
            decisions.append(ForeignWordDecision(
                word=w, action="absorbed",
                reason="vollständig absorbiert – keine Änderung"))
        else:
            decisions.append(ForeignWordDecision(
                word=w, action="leave",
                reason="einzelnes englisches Wort – Modell cross-lingual"))
    return decisions


def _english_run_at(text: str, start: int, end: int) -> int:
    """Anzahl aufeinanderfolgender NICHT-deutscher Wörter um die Position.

    Deutsche Wörter (Umlaute, Kernliste, deutsche Endungen) unterbrechen
    die Sequenz – „das Meeting mit dem Team“ ist kein Englisch-Block.
    """
    tokens = [(m.group(0), m.start(), m.end())
              for m in re.finditer(r"[A-Za-zÄÖÜäöüß'-]+", text)]
    idx = next((i for i, (w, s, e) in enumerate(tokens)
                if s <= start < e), None)
    if idx is None:
        return 0
    # Satzgrenzen zwischen Tokenpaaren brechen die Sequenz
    def _sentence_break(a, b):
        between = text[a[2]:b[1]]
        return bool(re.search(r"[.!?]", between))

    run = 1 if not _is_likely_german(tokens[idx][0]) else 0
    # nach links
    i = idx - 1
    while i >= 0 and not _is_likely_german(tokens[i][0]) and \
            not _sentence_break(tokens[i], tokens[i + 1]):
        run += 1
        i -= 1
    # nach rechts
    j = idx + 1
    while j < len(tokens) and not _is_likely_german(tokens[j][0]) and \
            not _sentence_break(tokens[j - 1], tokens[j]):
        run += 1
        j += 1
    return run


def apply_loanwords(text: str, language: str = "German") -> tuple[str, list]:
    """Wendet loanword_de-Entscheidungen an; gibt (Text, Ersetzungen)."""
    replacements = []
    if not language.lower().startswith("ger"):
        return text, replacements
    decisions = analyze_foreign_words(text, language)
    # Mehrwort-Begriffe zuerst („Deep Learning“), dann Einzelfunde
    decisions.sort(key=lambda d: -len(d.word))
    done_spans: list[tuple[int, int]] = []
    for decision in decisions:
        if decision.action == "loanword_de" and decision.replacement:
            w = decision.word
            pattern = re.compile(r"(?<![\wÄÖÜäöüß'])" + re.escape(w) +
                                 r"(?![\wÄÖÜäöüß'])")
            repl = decision.replacement

            def _r(m, repl=repl, text=text, done_spans=done_spans):
                if any(s <= m.start() and m.end() <= e for s, e in done_spans):
                    return m.group(0)
                before = text[max(0, m.start() - 2):m.start()]
                at_start = m.start() == 0 or before.rstrip().endswith(
                    (".", "!", "?", ":", ";", "\n"))
                out = repl[0].upper() + repl[1:] if at_start else repl
                replacements.append({"from": m.group(0), "to": out,
                                     "rule": "loanword"})
                done_spans.append((m.start(), m.end()))
                return out
            text = pattern.sub(_r, text)
    return text, replacements
