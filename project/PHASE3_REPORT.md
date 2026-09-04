# PHASE 3 COMPLETE — Referenz-erhaltende Optimierung der VD-E-Stimme

**VoiceOverApp 1.3.0** · Auftrag (§19–24): Die Human-Preferred-Reference
**VD-E / Sample I** ist eine sehr gute Grundlage und darf **nicht**
grundlegend verändert werden. Optimiert wurden ausschließlich:
Fach-/Fremdwort-Aussprache (höchste Priorität), subtile Emotion,
natürliche Variation, semantische Betonung — bei starrem
Referenz-Schutz und Voice-Guard.

---

## 1. Referenz-Schutz (§23 – REFERENCE-PRESERVING)

- Die VD-E-Referenz wird beim Phase-3-Lauf **gesperrt**:
  `benchmark/phase3/reference_lock.json` (SHA-256-Manifest). Vorhandene
  Referenz (dein Sample I) wird unverändert übernommen; existiert sie
  nicht, wird sie einmalig deterministisch erzeugt und dann gesperrt.
- **Alle Varianten verwenden denselben Clone-Prompt** — Stimme, Timbre
  und Tempo bleiben identisch; verändert sich nur Textebene und Sampling-
  Streuung.
- **Voice-Guard**: Median-F0 jeder Variante muss im Band 0,82–1,22 der
  Referenz-F0 liegen (zu tief/dunkel/theatralisch → Guard-Anschlag,
  Variante wird nicht empfohlen).

## 2. Höchste Priorität: Fremd-/Fachwörter (§20)

Neues Modul `app/pronunciation/tech_terms.py` (~130 kuratierte
Respellings + Komposita-Regel), TTS-intern (Originaltext bleibt
unverändert, §15). Betonung wird über **GROSSBUCHSTABen** markiert:

| Original | TTS-intern | Grund |
|---|---|---|
| Theorie | teo-RIE | verhindert engl. „th“, setzt Endbetonung |
| Quantentheorie | Quan-ten-teo-RIE | Nutzer-nannt (§20) |
| Kybalion | Kü-BA-li-on | Nutzer-nannt, korrekte Silben + Betonung |
| Relativitätstheorie | Re-la-ti-vi-täts-teo-RIE | Silbengliederung |
| Entropie / Philosophie / Phänomen / These … | En-tro-PIE / Fi-lo-so-FIE / Fä-NO-men / TEE-se | griech.-lat. Betonung |
| …feldtheorie (beliebig) | …-teo-RIE | generische Suffix-Regel |

- **Priorität**: Benutzerwörterbuch > Fachwort-Layer > Built-ins >
  Modell (getestet: eigener Wörterbucheintrag gewinnt).
- Echte englische Wörter („Thriller") und englische Sätze werden NICHT
  angetastet.
- **Unbekannte Fachwörter werden gemeldet, nicht geraten** (§13/§20):
  Suspekten-Erkennung (-theorie/-logie/-ität/-ismus/-forschung/…) →
  Bericht/Vorschlagsliste.

## 3. Subtile Emotion (§21 — Emotion ≠ Dramatisierung)

- 12 neue inhaltsausgelöste Zustände (Neugier, Nachdenklichkeit,
  Überraschung, Spannung, Bedrohlichkeit, Staunen, Ruhe, Zuversicht,
  Zweifel, Erkenntnis, Skepsis, Ernst) als kurze, dezente
  Instruct-Zeilen — nur wenn der **Inhalt** sie auslöst (Musterliste),
  budgetiert über das Phase-2-Hinweis-Budget (keine Global-Emotion).
- **Clone-Modus** (VD-E hat keinen Instruct-Kanal): Emotion wirkt über
  semantisch motivierte Sampling-Offsets (max. +0,08 Temperatur, eng
  begrenzt 0,55–0,92) — referenz-erhaltend.
- **Bug-Fix mit echter Wirkung**: Das englische Emotions-Muster „war"
  (somber) matchte das deutsche Wort „war" — deshalb klangen z. B.
  Fragesätze („…gestellt war?") fälschlich düster/angestrengt. Muster
  sind jetzt sprachgetrennt (DE/EN).

## 4. Natürliche Variation (§22)

- Rollenabhängige Sampling-Offsets (dramatisch +0,08 … ruhig −0,02),
  aktiviert per Default **nur für Clone-Stimmen** (CustomVoice erhält
  Variation über Instructs).
- `variation_report()` misst Langform-Monotonie: F0-Spread über Segmente
  („identische Tonhöhe"), Pausen-CV, Tempo-CV — Teil des Phase-3-
  Vergleichs.
- Neue Variations-Batterie: vier strukturgleiche Sätze („Sieben Gesetze
  tragen …") prüfen Melodie-Vielfalt gezielt.

## 5. Semantische Betonung (§19.7)

- `emphasis_targets()`: 1–2 Schlüsselwörter je Satz (Salienz-Nomina +
  Superlative; **negierte Begriffe werden übersprungen**; deutsche
  Satzende-Gewichtung/Rhema), fließt als sanfter Hinweis in den
  Instruct (nur CustomVoice) und in die QC-Bewertung.

## 6. Vergleichsdesign & Ablauf (auf RTX 5060)

Varianten (alle mit identischer VD-E-Stimme):

| Variante | Fachwörter | Sampling-Variation |
|---|---|---|
| BASE (Vorher) | aus | aus |
| TECH | **an** | aus |
| VAR | aus | **an** |
| TECHVAR | an | an |

Batterien: TECH (6 Fachwortsätze, inkl. deiner drei Begriffe), EMOTION
(12 Zustände), VARIATION (4 strukturgleiche Sätze), MELODY (Rollenmix),
LONG (Kybalion komplett, als Hördatei je Variante).

```
START.bat → Erweitert → „Phase 3 – VD-E verfeinern“
  [▶ Phase-3-Vergleich starten]        # bzw. --phase3-run
  Blindproben (A–D) anhören → wählen   # bzw. --phase3-pick C
  [Übernehmen]                          # bzw. --phase3-apply
```
`--phase3-apply` setzt **nur Schalter** (`tech_germanization`,
`variation.enabled`) — die Stimme bleibt VD-E, garantiert (§23).

## 7. Testergebnis

**122/122 bestanden** (103 Bestand + 19 neue Phase-3-Tests: Fachwort-
Germanisierung inkl. Nutzer-Begriffe, Priorität, Suspekten-Meldung,
Original-Schutz, subtile Emotionen + Budget, „war"-Bug, Sampling-
Offsets, Betonungs-Ziele (Negations-Skip), Monotonie-Detektor,
Referenz-Lock (Hash-Stabilität), Voice-Guard, Vergleichs-Mechanik,
Auswahl/Übernahme (nur Schalter), Clone-Default, UI-Ende-zu-Ende).
Keine Regressionen: Batch/Cache/Resume/WAV/MP3/QC/UI weiterhin grün.

**Ehrliche Grenze (§22/§38-Geist):** Ob TECHVAR die BASE-Variante
akustisch schlägt, entscheidet der A/B-Lauf auf deiner RTX 5060 + dein
Blindvergleich — hier nur Mechanik und Referenz-Schutz verifiziert.
Falls BASE gewinnt, bleibt alles wie bisher (Schalter aus).

## 8. Bekanntes / Empfehlung

1. Falls einzelne Fachwort-Respellings im Ohr abweichen: einfach in
   `pronunciation/pronunciation.json` eintragen (gewinnt immer) — z. B.
   `"Kybalion": "Ki-BEI-li-on"`, falls du diese Lesart bevorzugst.
2. VD-B-DIRECT-Erkenntnis aus Phase 2 gilt weiter: Clone-Pfad hat keinen
   Instruct-Kanal — Emotion dort bleibt indirekt (Text + Sampling).
   Die Phase-3-Batterien messen genau diese Differenz.
3. Nächster sinnvoller Schritt (nach deinem Hörurteil): Whisper-ASR-QC
   (lokal) für Wort-für-Wort-Verifikation der Fachbegriffe.
