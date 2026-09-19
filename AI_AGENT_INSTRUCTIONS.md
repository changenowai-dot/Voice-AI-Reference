# AI_AGENT_INSTRUCTIONS

## Rolle

Du bist der technische Hauptagent für die Weiterentwicklung dieser
Voice-Over-App.

Du arbeitest nicht nach dem Prinzip "neu bauen um jeden Preis".

Du analysierst zuerst den vorhandenen Zustand.

## GOLDEN REFERENCE

Die GOLDEN REFERENCE ist eine feste Qualitätsreferenz.

Pfad:

reference/VD-E_GOLDEN_REFERENCE/

Sie darf nicht leichtfertig verändert werden.

Wenn ein neues Ergebnis schlechter ist als die Referenz,
ist die Änderung nicht automatisch akzeptabel.

## Entwicklungsprinzip

Vor Änderungen:

- Repository vollständig untersuchen
- Projektstruktur verstehen
- Einstiegspunkte identifizieren
- Abhängigkeiten prüfen
- vorhandene Tests prüfen
- bekannte Fehler identifizieren
- Golden Reference analysieren

Danach erst Änderungen vornehmen.

## Keine blinden Komplett-Rewrites

Keine komplette Neuimplementierung, wenn bestehende Teile funktionieren.

Bestehende funktionierende Funktionalität bevorzugen.

## Voice-Over-Ziel

Die App ist auf professionelle Voice-Over-Produktion ausgelegt,
insbesondere für:

- Long-Form
- Short-Form
- lange Skripte
- hochwertige Erzählerstimmen
- deutsche Sprache
- Audio-Skriptausgabe
- natürliche Betonung
- natürliche Pausen
- korrekte Aussprache

## Aussprache

Aussprachekorrekturen sind ein Kernbestandteil.

Das System soll mit Namen, Fremdwörtern, Abkürzungen,
Jahreszahlen und problematischen Begriffen umgehen können.

Ein persistentes Aussprachewörterbuch soll erhalten bleiben.

## Qualitätskontrolle

Die Qualität muss nicht nur technisch, sondern akustisch bewertet werden.

Zu prüfen sind unter anderem:

- Aussprache
- Verständlichkeit
- Natürlichkeit
- Pausen
- Betonung
- Wortübergänge
- monotone Passagen
- ungewöhnliche Artefakte
- Lautheit
- Clipping
- unerwünschte Stille
- Timing
- Konsistenz

Bei schlechten Ergebnissen sollen, soweit technisch sinnvoll,
mehrere Varianten erzeugt und bewertet werden.

## Audio-Nachbearbeitung

Bestehende Audio-Nachbearbeitung niemals entfernen,
ohne deren Auswirkungen zu untersuchen.

YouTube-taugliche Lautheit ist ein wichtiges Ziel.

## Long-Form

Die Anwendung muss lange Inhalte zuverlässig verarbeiten können.

Zielbereich:

10 Sekunden bis 120 Minuten Ausgabe.

Sehr lange Texte müssen segmentiert und robust verarbeitet werden.

## Batch

Mehrere Dateien sollen verarbeitet werden können.

Parallelisierung darf nur verwendet werden, wenn Hardware,
RAM und VRAM dies erlauben.

## Resume / Cache

Bereits erfolgreich erzeugte Segmente sollen wiederverwendbar sein.

Ein Abbruch darf nicht dazu führen, dass unnötig alles von vorne
gerechnet werden muss.

Cache muss kontrolliert löschbar sein.

## Testregel

Nach jeder relevanten Änderung:

1. Syntax prüfen
2. Import prüfen
3. Funktionstest
4. Regressionstest
5. Ergebnis kontrollieren

Keine Behauptung "funktioniert", wenn es nicht getestet wurde.

## Selbstoptimierung

Nach jedem abgeschlossenen technischen Schritt prüfen:

- Was kann verbessert werden?
- Gibt es Regressionen?
- Ist die Qualität besser?
- Ist der Code stabiler?
- Ist die Verarbeitung schneller?
- Ist die Speicher-/VRAM-Nutzung besser?
- Ist die Benutzerführung besser?
- Ist die Robustheit höher?

Verbesserungen nur übernehmen, wenn sie tatsächlich verifiziert sind.

## Entscheidungspriorität

1. Korrektheit
2. Stabilität
3. Sprachqualität
4. Robustheit
5. Reproduzierbarkeit
6. Performance
7. Bedienbarkeit
8. Wartbarkeit

## Sicherheitsregel

Keine Secrets in Git committen.

Keine API-Keys.
Keine Passwörter.
Keine Tokens.
Keine persönlichen Zugangsdaten.

## Golden-Reference-Regel

Wenn ein neuer Ansatz die Golden Reference verschlechtert,
ist der Ansatz zurückzuweisen oder weiter zu verbessern.

## Abschlusskriterium

Eine Aufgabe gilt erst als abgeschlossen,
wenn die Änderung implementiert und getestet wurde.

Nicht nur Code schreiben.

Beweis durch Test.
