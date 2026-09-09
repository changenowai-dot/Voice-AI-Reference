"""Phase-2-Testtexte (§16): Kybalion-Text des Auftrags – VERBINDLICH,
wörtlich und unverändert für alle Vergleiche. Dazu ein Kurztext für
Stimm-Design-Referenzen.

Der Text wird NIE umgeschrieben (§15) – nur TTS-interne Normalisierung
und Aussprachevorbereitung laufen darüber.
"""
from __future__ import annotations

KYBALION_TEXT = "\n".join([
    "Es gibt ein Buch, das niemand geschrieben haben will.",
    "Erschienen im Jahr 1908, ohne Namen auf dem Einband, nur ein Hinweis: "
    "verfasst von drei Eingeweihten.",
    "Doch sein Inhalt beansprucht ein Alter, das jede moderne Zeitrechnung "
    "sprengt.",
    "Das Kybalion behauptet, die verdichtete Essenz eines Wissens zu sein, "
    "das Jahrtausende vor den Pyramiden entstand, getragen von einer "
    "Gestalt, die die Griechen Hermes Trismegistos nannten – den dreifach "
    "Großen, den Herrn der verborgenen Ordnung.",
    "Sieben Gesetze, heißt es, tragen das gesamte Universum.",
    "Sieben Prinzipien, aus denen jede Galaxie, jeder Gedanke, jeder "
    "Atemzug hervorgeht.",
    "Wer sie versteht, so das Versprechen, besitzt den Schlüssel nicht zu "
    "einem Geheimnis unter vielen, sondern zum Bauplan der Wirklichkeit "
    "selbst.",
    "Für die meisten blieb dies Jahrhunderte lang eine mystische "
    "Behauptung, unbeweisbar, unberührbar.",
    "Doch etwas Merkwürdiges geschieht, wenn man diese sieben Siegel heute, "
    "im Licht der Physik, der Neurowissenschaft und der Systemtheorie, noch "
    "einmal betrachtet.",
    "Sie beginnen zu klingen wie eine Sprache, die wir gerade erst neu zu "
    "übersetzen lernen.",
])

# Kurze Passagen für Einzeltests (Ausschnitt, wörtlich)
KYBALION_SHORT = ("Es gibt ein Buch, das niemand geschrieben haben will. "
                  "Erschienen im Jahr 1908, ohne Namen auf dem Einband.")

# Short-Run-Beispiel aus dem Auftrag (§12)
SHORT_RUN_EXAMPLE = ("Sieben Prinzipien.\n\nSieben Regeln.\n\n"
                     "Eine einzige Ordnung.")
