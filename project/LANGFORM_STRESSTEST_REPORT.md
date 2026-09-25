# Langform-Stresstest „Stein der Weisen" — Bericht

**Datum:** 2026-09-24 · **Zweig:** `arena/01a0ce4d-voice-ai-reference`
**Text:** `input/stein_der_weisen_LANGFORM.txt` — 15.256 Zeichen, 2.255 Wörter,
42 Absätze, bytegetreu übernommen (keine Vereinfachung, keine Kürzung).
**Sprache erkannt:** German (Score 0.473 vs. English 0.029).
**Pipeline-Spiegel:** `process_file()` — load_config → advanced →
`_resolve_segment_config` → analyze → normalize+PronunciationEngine →
segment_text → `_resolve_pause_settings`/`_resolve_speed` → assign_pauses.

**Ergebnis in einem Satz:** Der Text läuft ohne Textverlust durch die
Pipeline (0 fehlende, 0 zusätzliche Wörter, in beiden Varianten), und der
Stresstest hat **drei echte Produktionsdefekte aufgedeckt und behoben** —
ohne dass ein Anchor, eine Aussprache-Optimierung oder die Golden Reference
gelitten hätte.

---

## Vorausgegangen: Sandbox-Reset (2×)

Die Git-Historie wurde zwischen den Turns erneut auf den Klon-Zustand
zurückgesetzt; Arbeitsdateien und der neue Stresstext überlebten. Sämtliche
Arbeit wurde re-committet:

| Commit | Inhalt |
|---|---|
| `e5aeb1b` | Pronunciation Batches 3–5 + Kaskaden-Audit gesichert |
| `85c8b18` | Pacing-Fixes (Segmentierung 130/35/200, `_group_items`, `_resolve_speed`, conftest-Schutz) |
| `a613609` | Stresstext bytegetreu eingecheckt |
| `11818b9` | **3 neue Stresstest-Fixes** (dieser Bericht) |
| `891ef29` | Benchmark-Ausgabeordner ignoriert |

## Die drei im Stresstest aufgedeckten Defekte (behoben in `11818b9`)

**D1 — „+++++"-Separatoren wurden vorgelesen.**
`split_blocks` klassifizierte die 17 Trennzeilen als *heading level 3*
(kurz, kein Satzzeichen, `"+".islower()` ist False). Die Normalisierung
expandiert `+` → „plus": **die Stimme hätte 17× „plus plus plus plus plus"
gesprochen**, jeweils mit Überschriften-Pause. Fix: `_is_separator_line()`
(reine Symbolzeilen = Abschnittsgrenze, kein Sprechtext) + Headings müssen
mindestens einen Buchstaben enthalten. Nachweis: 42 Paragraph-Blöcke,
0 „+"-Blöcke, „plus" 0-mal im TTS-Text, echte Überschriften (`# x`,
`Kapitel 2`) unverändert, test_textstack 10/10.

**D2 — 1-Wort-Orphan + Phrase-mitten-Schnitt im Wortfallback.**
Der kommalose 203-Zeichen-Satz („Wir sind von den staubigen Papyrusrollen
…") wurde im Wortfallback gierig bis max_chars gefüllt → Segment [195 Z] +
8-Zeichen-Einzelsegment „gereist.", Schnitt direkt vor dem letzten Wort
(„… modernen FY-sik | gereist."). Fix: Koordinations-Split vor
„und/oder/aber/sondern/sowie/bzw + and/but/or/yet" (byte-identisch) und
`_rebalance_tiny_tail()` für den harten Wortfallback. Ergebnis: **[149, 53]**
(„… bei C G Jung | und in die Quantenwelten …").

**D3 — Platzhalter überschrieb die Live-Voice-Referenz.**
Nach dem Cache-Verlust des Resets schrieb ein Benchmark-Lauf eine
571.472-Byte-Platzhalter-`VD-E.wav` (SHA `7e6cd36e…` statt `b156c02a…`).
Der conftest-Schutz half nicht, weil beim Session-Start keine Baseline
existierte. Fix: conftest setzt `cache/voice_refs/VD-E.wav` + `vd_e.wav`
am Session-Ende **zwingend auf die Golden Reference**. Bewiesen: nach einem
weiten Phase2-Polluter-Lauf bleiben beide Pfade `b156c02a…`. Alle vier
Referenz-Kopien verifiziert: `b156c02a60a873ad…`.

---

## 1) LANGSATZ-STABILITÄT

Längste Quellsätze (nach Normalisierung, inkl. Zahlwörtern):

| Zeichen | Wörter | geschätzt | Kommata | >25 W |
|---|---|---|---|---|
| 219 | 30 | 15,9 s | 4 | JA |
| 203 | 33 | 14,7 s | 0 | JA |
| 187 | 25 | 13,6 s | 3 | nein |
| 179 | 28 | 13,0 s | 5 | JA |
| 174 | 22 | 12,6 s | 0 | nein |

Nur **5 von 165** Sätzen überschreiten 25 Wörter; nur **2** überschreiten
200 Zeichen — beide werden zuverlässig an Klausel-/Koordinationsgrenzen
geteilt (Blei-Atom-Satz → Komma-Chunk mit `after_comma`-Pause;
Papyrusrollen-Satz → [149, 53]).

**Varianten-Vergleich (messbar):**
- **A (alt, 420/120/700):** längstes Segment **573 Z = 41,5 s**, 38 von 43
  Segmenten > 200 Z. Ein 41-s-Block ist genau die Struktur, in der
  Tempodrift/Tonkollaps im letzten Drittel entstehen kann.
- **B (neu, 130/35/200):** längstes Segment **194 Z = 14,1 s**, 0 Segmente
  > 200 Z, max. unter dem 14,5-s-Limit.

**Grenze:** Ob die Stimme *innerhalb* eines Blocks tatsächlich schneller
wird, ist akustisch und hier **nicht messbar** (kein GPU/TTS, torch-Stub).
Die strukturelle Voraussetzung — kein Segment länger als ~14 s — ist in B
erfüllt; der Abhör-Protokoll unten prüft den Rest am Host.

## 2) PAUSEN

B: **146,5 s Pause = 11,9 % der Laufzeit**, Ø **0,88 s pro Satz**
(A: 74,3 s = 6,4 %, Ø 0,45 s). 102 verschiedene Pausenwerte von 111
(keine mechanische Gleichfolge, `diagnose_pause_plan`: mechanical=0,
long=[]). Min/Ø/max 0,47/1,32/2,18 s — **natürliche Streuung, keine
Gleichschaltung, keine Deckenpuffer**. Abschnittsgrenzen (die ehemals
„+++++") atmen über die normale Absatz-Pause (relaxed ~1,76 s) statt über
gesprochene Symbole. Klausel-Pausen im EN- und DE-narrative-Zweig sind
verified (after_comma 0.28/0.30 … after_ellipsis 0.70/0.9).

## 3) SEGMENTIERUNG

| Metrik | A lang (420/120/700) | B kurz (130/35/200) |
|---|---|---|
| Segmente | 43 | 111 |
| Zeichen min/Ø/max | 32/350/**573** | 32/135/**194** |
| Dauer min/Ø/max (s) | 2,3/25,4/**41,5** | 2,3/9,8/**14,1** |
| Klausel-Segmente | **0** | 1 (+ Koordinations-Split) |
| Pausenanteil | 6,4 % | 11,9 % |
| leere Segmente / über Limit | 0 / 0 | 0 / 0 |
| **Textverlust (Wörter)** | **0/0** | **0/0** |
| Sprechzeit gesamt | 18,20 min | 18,12 min |

B bevorzugt Satzgrenzen (Ø 135 Z ≈ 1 Satz) und öffnet nur bei >200-Z-Sätzen
Klauselgrenzen. 167 gegen 165 Satz-Zählungen = genau die 2 geteilten
Übersatz-Sätze; der zusammengefügte Segmenttext ist **byte-identisch** mit
der Quelle.

## 4) LANGFORM-KONSISTENZ (ANFANG/MITTE/ENDE, Variante B)

| Drittel | Segmente | Dauer Ø/max | Pausenanteil | Wörter/Seg |
|---|---|---|---|---|
| ANFANG | 37 | 10,7 s / 14,1 s | 11,0 % | 22,1 |
| MITTE | 37 | 9,4 s / 13,6 s | 11,7 % | 18,1 |
| ENDE | 37 | 9,2 s / 14,1 s | 13,0 % | 19,5 |

Strukturell gleichmäßig über den gesamten Textverlauf (A: 27,6/29,0/19,9 s
Ø mit 41,5-s-Spitze im Anfang). Akustische Drift (Loudness/Artikulation/
Tonhöhe) ist host-seitig zu verifizieren — Protokoll unten.

## 5) FACHBEGRIFFE

41 Begriffe aus der Aufgabenliste durch normalize+Engine geprüft:
**29× IDENTITY** — darunter alle harten Anker im Text (Atom/Atome/Atomkerne,
Protonen, Neutronensterne, Quantenphysik, Quantenmechanik, mathematische,
Theorie, Bewusstsein, Psychologie/Psychiater, Wissenschaft) und die
Alchemie-Termini (Lapis Philosophorum, Hermes Trismegistus, Mikro-/Makrokosmos,
Prima Materia, Opus Magnum, Nigredo, Albedo, Citrinitas, Rubedo, Unio Mystica,
Individuation, Transmutation als Dokument-Respell).
12 Nicht-Identity-Fälle sind **ausnahmslos dokumentierte Produktions-Einträge**
(nachgewiesen): Smaragdtafel/Smaragd/Tabula Smaragdina (builtins_de.json
192–194), Kern-fy-SIK (tech_terms.py 253, Batch 4), -lo-GIE-Familie
(Neurobiologie, Tiefenpsychologie), Einstein→Ainstein (builtins 64),
Phänomen→Fä-NO-men, E=mc²→„E gleich mc²" (Formel-Normalisierung),
C.G.→C G (Initialen), 82/79→Zahlwörter. **Keine neuartige Mutation.**
Ob „pü-che" (Psyche, builtins 139) und „FY-sik" (Physik, tech_terms 61)
akustisch gut sind, entscheidet der Host-A/B — Sichtbewertung zählt laut
Vorgabe nicht.

## 6) DEUTSCHER REGRESSIONSTEST

`/home/user/.qa/anchors.py` (rekonstruiert, reiner Lese-Lauf, kein
clear_all): **ALLE 26 harten Anker OK** — isoliert, satzinitial, mid-sentence,
Plural/Kontext. Die 6 „Abweichungen" sind ausschließlich die satzinitiale
Großschreibung der isolierten Probe (mathematisch*/psychologisch);
mid-sentence byte-identisch. Wissenschaft-Familie: Wissenschaft/
Wissenschaftler/Wissenschaftsgeschichte/**Neurowissenschaft IDENTITY**;
Natur-/Geisteswissenschaft = dokumentierte Respells (unverändert zum
Baseline-Befund). Tests: test_pronunciation 6/6,
test_pronunciation_cascade 27/27, test_phase3 21/21.

## 7) PRESET-VERGLEICH (gemessen, neue Segmentierung, 111 Segmente)

| Preset | style/strategy | speed | Pausen | s/Satz |
|---|---|---|---|---|
| deep_documentary | relaxed/narrative | 1,00 | 146,3 s (11,9 %) | 0,88 |
| de_documentary | relaxed/narrative | 1,00 | 146,3 s (11,9 %) | 0,88 |
| **psychological** | relaxed/**classic** | **0,97** | 95,7 s (8,1 %) | 0,57 |
| cinematic | relaxed/classic | 0,95 | 96,7 s (8,2 %) | 0,58 |
| calm_storytelling | relaxed/classic | 0,95 | 96,7 s (8,2 %) | 0,58 |
| audiobook | auto/classic | 1,00 | 72,5 s (6,3 %) | 0,43 |
| documentary | auto/classic | 1,00 | 72,5 s (6,3 %) | 0,43 |

**Analyse ohne Blindübernahme:** „psychological" unterscheidet sich in drei
Eigenschaften: (a) klassische Pausenstrategie → **weniger** Luft (0,57
gegen 0,88 s/Satz), (b) Tempo 0,97, (c) pacing_hint. Wegen des
durch `_resolve_pause_settings`/`_resolve_speed` behobenen Shadowing
bekommt **jedes** Preset jetzt seine eigenen Werte — das frühere
„psychological klang ruhiger" ist mit (b)+(c) vereinbar, während (a) allein
das Gegenteil erwarten ließe. deep_documentary liefert mit narrative +
pacing_hint die meiste Atemluft bei unverändertem Tempo 1,00.
**Empfehlung an den Host-A/B:** beide Presets auf dem Stresstext hören;
Entscheidungskriterium Kap. 8, nicht das Label.

## 8) ENTSCHIEDENES KRITERIUM

Struktur-Seite vollständig erfüllt: kein Segment > 14,1 s, gleichmäßige
Drittel, Pausen ohne Drift-Tendenz, 0 Textverlust. **Akustisch (Tempo-
Kurve, Tonlage, Artikulation ANFANG→MITTE→ENDE) ist im Sandbox-Umfeld
keine Messung möglich** (torch-Stub, keine GPU). Dafür das Host-Protokoll:

1. Variante B mit `deep_documentary` generieren (config unverändert lassen:
   target 130 steht bereits in DEFAULT_CONFIG).
2. Drei 30-s-Fenster schneiden: **ANFANG** (Seg. 1–3), **MITTE**
   (Newton-Teil, Seg. ~55), **ENDE** (letzte 3 Segmente).
3. Je Fenster prüfen: Tempo konstant? letzte Wörter nicht gequetscht?
   Melodie hält bis zum Schluss? Artikulation im letzten Drittel intakt?
4. A/B gegen Variante A (420/120/700 via `advanced.segment_target_chars` etc.
   — wird vom Resolver bewusst als Nutzerwert respektiert) **oder** Preset
   `psychological`; gleiche Fenster.
5. Nebenbei hören: die 17 Abschnittsgrenzen (ehem. „+++++") — dort muss
   **Pause** sein, kein „plus plus plus".

---

## Test- und Integritätsstand nach allen Änderungen

- test_textstack 10/10 · test_segmentation_prosody 10/10 ·
  test_pronunciation 6/6 · test_pronunciation_cascade 27/27 ·
  test_phase3 21/21 · test_phase2 15/17 (= dokumentierte Baseline 2F)
- 26 harte Anker OK · Golden Reference 4× `b156c02a…` ·
  config.json: BOM, speed 1.0, target 130 · Arbeitsbaum clean
- Belastungsprobe: 634-Zeichen-Satz ×3 → 9 Segmente, 24/24 Kommata,
  0 leer, 0 über Limit, 6 Klauselenden.
