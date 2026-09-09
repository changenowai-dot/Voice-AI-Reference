"""Reproduzierbare deutsche Testtexte für Baseline & A/B (Anforderung 5+30).

12 deterministische Texte (GERMAN-01 … GERMAN-12), die die geforderten
Kategorien abdecken. Die Baseline (`benchmark/baseline/`) wird mit
diesen Texten erzeugt und geht NIEMALS verloren; jede Optimierung wird
dagegen verglichen.
"""
from __future__ import annotations

GERMAN_TEXTS: list[dict] = [
    {
        "id": "GERMAN-01", "category": "Dokumentation",
        "text": ("Im Sommer 1934 begann in den trockenen Hügeln östlich von "
                 "Istanbul eine Ausgrabung, die niemand für möglich gehalten "
                 "hatte. Die Archäologen arbeiteten acht Jahre lang, bevor "
                 "sie verstanden, was sie tatsächlich gefunden hatten."),
    },
    {
        "id": "GERMAN-02", "category": "Psychologie",
        "text": ("Die Psyche des Menschen ist kein Archiv, sondern eine "
                 "Werkstatt. Was wir Verdrängung nennen, beschrieb Sigmund "
                 "Freud 1915 erstmals systematisch – doch die Frage, warum "
                 "Gefühle verschwinden, ohne dass wir es bemerken, ist bis "
                 "heute nicht restlos geklärt. Attachment-Forschung und "
                 "Behavior-Studien liefern inzwischen Teile der Antwort."),
    },
    {
        "id": "GERMAN-03", "category": "Jahreszahlen & Zahlen",
        "text": ("1914 begann der Erste Weltkrieg, 1939 der Zweite, 1945 "
                 "endete er, 1989 fiel die Mauer, 2001 veränderte sich die "
                 "Welt, und 2026 stehen wir vor neuen Fragen. Das 20. "
                 "Jahrhundert forderte rund 100 Millionen Tote, davon allein "
                 "1,5 Milliarden verlorene Lebensjahre – 50 % davon in nur "
                 "2,5 % der Kriegsjahre. 3,14 wirkt daneben wie eine kleine "
                 "Zahl."),
    },
    {
        "id": "GERMAN-04", "category": "Eigennamen",
        "text": ("Friedrich Nietzsche und Søren Kierkegaard lasen "
                 "Descartes, während Foucault später Voltaire und "
                 "Rousseau neu deutete. Stephen Hawking erklärte Einstein, "
                 "und Marie Curie öffnete mit Röntgen ein Jahrhundert. Von "
                 "Göbekli Tepe bis Machu Picchu reichen die Namen dieser "
                 "Geschichte – Ludwig XIV. hätte es gefallen."),
    },
    {
        "id": "GERMAN-05", "category": "Fremdwörter",
        "text": ("Das Meeting war angesetzt, die Deadline näher, das Feedback "
                 "vernichtend. Deep Learning verändert die Psychology, das "
                 "Mindset einer ganzen Generation – und während das Team "
                 "sein Burnout managte, schrieb die Community ihr Statement. "
                 "\"The quick brown fox jumps over the lazy dog\" blieb "
                 "dabei vollkommen unübersetzt."),
    },
    {
        "id": "GERMAN-06", "category": "Abkürzungen",
        "text": ("u.a. wegen z.B. der ADHS-Diagnosen, v.a. bei der NASA und "
                 "im CERN, wurde das u.s.w. untersucht – inkl. der CPU-"
                 "Temperatur, gemessen in ms, dokumentiert von Dr. Müller "
                 "aus z. B. München, ca. 14:30 Uhr, ca. 3 Mrd. Messwerte, "
                 "u.U. auch am 1. Mai, d.h. vor dem Wochenende."),
    },
    {
        "id": "GERMAN-07", "category": "Lange Sätze",
        "text": ("Wer immer wieder versucht, die leise bröckelnde Ordnung "
                 "seiner Erinnerungen gegen die stürmische Flut der "
                 "Vergessenheit zu verteidigen, der wird irgendwann "
                 "bemerken, dass nicht die großen Momente bleiben, sondern "
                 "die unscheinbaren, die sich niemand bewusst ausgesucht "
                 "hat, die sich einfach eingestellt haben, wie Gäste, die "
                 "leise bleiben und doch für immer wohnen bleiben wollen, "
                 "obwohl niemand sie je eingeladen hat."),
    },
    {
        "id": "GERMAN-08", "category": "Rhetorische Fragen",
        "text": ("Warum wiederholen Menschen Muster, die sie längst "
                 "durchschaut haben? Was geschieht wirklich, wenn wir "
                 "vergessen? Und wer entscheidet eigentlich, welche "
                 "Erinnerung bleibt – wir, oder die Zeit? Die Antwort "
                 "verändert alles, was wir über uns glauben."),
    },
    {
        "id": "GERMAN-09", "category": "Emotionale Passage",
        "text": ("In dieser Nacht, zum letzten Mal, hielt er die Hand "
                 "seines Vaters. Plötzlich war alles anders. Nie wieder "
                 "würde dieses Haus so klingen wie früher, und die "
                 "Verzweiflung, die er so lange verdrängt hatte, kam "
                 "zurück – leise, geduldig, unerbittlich. Doch in ihr lag "
                 "auch eine seltsame Hoffnung."),
    },
    {
        "id": "GERMAN-10", "category": "Long-Form-Konsistenz",
        "text": ("Kapitel eins: Der Anfang\n\n"
                 "Es begann wie jede andere Geschichte: mit einer Frage, "
                 "die niemand stellte. Die Stadt schlief, die Laternen "
                 "flackerten, und irgendwo hinter einem Fenster saß ein "
                 "Mensch, der nicht schlafen konnte. Er dachte über das "
                 "Vergessen nach, über die Mechanismen der Erinnerung und "
                 "über die Frage, warum gerade die stillen Momente "
                 "bleiben.\n\n"
                 "Kapitel zwei: Die Wende\n\n"
                 "Dann, an einem Morgen im November, änderte sich alles. "
                 "Ein Brief ohne Absender, ein Datum ohne Jahr, ein Name, "
                 "den er nie gehört hatte: Orpheus. Die Psychologie hätte "
                 "gesagt: Projektion. Die Philosophie hätte geschwiegen. "
                 "Aber die Geschichte hatte längst ihren eigenen Willen "
                 "entfaltet, und er folgte ihr – hinab in die Tiefe seiner "
                 "eigenen Erinnerung, wo die Wahrheit geduldig wartete."),
    },
    {
        "id": "GERMAN-11", "category": "Mystery/Dramaturgie",
        "text": ("Das Verlies lag vierhundert Meter unter dem Eis. Kein "
                 "Signal, kein Licht, keine Spur. Doch an den Wänden fanden "
                 "sicher die Forscher Zeichen – elftausendfünfhundert Jahre "
                 "alt, arrangeiert in einem Muster, das keine Sprache "
                 "kennt. Wer hatte sie hinterlassen? Und vor allem: Warum?"),
    },
    {
        "id": "GERMAN-12", "category": "Kontraste & Aufzählung",
        "text": ("Erst kam der Zweifel, dann die Erkenntnis, schließlich die "
                 "Ruhe. Er wollte gehen, aber er blieb. Nicht die Lautstärke "
                 "machte den Unterschied, sondern die Stille danach. Genau "
                 "in diesem Moment, ausgerechnet jetzt, verstand er es."),
    },
]


def texts_for_ids(ids: list[str]) -> list[dict]:
    wanted = set(ids)
    return [t for t in GERMAN_TEXTS if t["id"] in wanted]


def category_map() -> dict:
    return {t["id"]: t["category"] for t in GERMAN_TEXTS}
