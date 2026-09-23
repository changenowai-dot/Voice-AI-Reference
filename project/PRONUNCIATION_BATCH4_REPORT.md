# VoiceOverApp — Fachwort-Batch 4: Verifikation der Nutzer-Prioritätenliste & ein echter Produktionsbug

Datum: 2026-09-23
Zweig: `arena/01a0ce4d-voice-ai-reference` (Teil A, `changenowai-dot/Voice-AI-Reference`)
Vorgänger: `PRONUNCIATION_BATCH3_REPORT.md` (Commit `809818c`)

---

## 0. Ausgangslage und Auftrag

Der Nutzer hatte nach Batch 3 einen **echten Qwen-Lauf auf der RTX 5060** gemacht und
zugehört. Ergebnis: *die meisten Begriffe sind bereits gut.* Auftrag dieser Runde:
nur die tatsächlich verbleibenden Problemfälle finden und mit minimalen
Produktionsänderungen beheben — großer Testaufwand, kleine Eingriffe.

Genannte Prioritäten: Daten, Prozessor, Philosoph/Philosophen/Philosophie/philosophisch,
Matrix/Matrizen/Matrixrechnung, Erkenntnistheorie/erkenntnistheoretisch/Erkenntnis,
Logarithmus/Logarithmen/logarithmisch, Vektor/Vektoren/Vektorraum/Vektorräume,
Gleichung/Gleichungen/Differentialgleichung/Bewegungsgleichung/Wellengleichung,
Quellcode/Quellcodes/Quelltext/Quelltexte, Metaphysik/metaphysisch,
Ontologie/ontologisch.

**Netto-Produktionsänderung dieser Runde: 1 Bug-Fix** (erfundenes Fugen-s),
**1 Test-Hygiene-Fix mit Produktionswirkung** (Wörterbuch-Pollution),
**2 veraltete Tests korrigiert**, **1 A/B-Harness neu**, **6 Tests neu/erweitert**.
Keine einzige Betonungs- oder Silbenregel wurde „auf Verdacht" geändert.

---

## 1. Phase 1 — Objektive Prüfung der Nutzer-Prioritätenliste

Gemessen über den vollen Produktionspfad (`PronunciationEngine.process` nach
`normalize_text`), nicht über die Regelwerte allein. 37 Formen, 11 Familien:

| Familie | Formen | Zustand |
|---|---|---|
| Daten | Daten, Datensatz | Identity — natürliche Orthographie |
| Prozessor | Prozessor, Prozessoren, Mikroprozessor | Identity / ohne Regel |
| **Philosoph** | **Philosoph, Philosophen, Philosophin, Philosophinnen, Philosophie, philosophisch** | **alle 6 aktiv umgeschrieben** |
| Matrix | Matrix, Matrizen, Matrixrechnung | Identity / ohne Regel |
| Erkenntnis | Erkenntnistheorie, erkenntnistheoretisch, Erkenntnis | Identity / ohne Regel |
| Logarithmus | Logarithmus, Logarithmen, logarithmisch | Identity |
| Vektor | Vektor, Vektoren, Vektorraum, Vektorräume | Identity / ohne Regel |
| Gleichung | Gleichung, Gleichungen, Differential-, Bewegungs-, Wellengleichung | Identity / ohne Regel |
| Quellcode | Quellcode, Quellcodes, Quelltext, Quelltexte | Identity / ohne Regel |
| Metaphysik | Metaphysik, metaphysisch | Identity / ohne Regel |
| Ontologie | Ontologie, ontologisch | Identity / ohne Regel |

**Befund: von 37 geprüften Formen sind genau 6 aktiv umgeschrieben — alle 6 gehören
zur Philosoph-Familie.**

Das deckt sich mit dem Höreindruck des Nutzers und ist die Begründung, warum diese
Runde **keine** Regel für Daten, Prozessor, Matrix, Erkenntnis, Logarithmus, Vektor,
Gleichung, Quellcode, Metaphysik oder Ontologie anfasst: Diese Formen gehen bereits
als natürliche Orthographie an das TTS. Es gibt dort nichts zu korrigieren, und ein
Eingriff wäre eine Verschlechterung ohne Beleg.

Die Philosoph-Familie bleibt die einzige, die vom Quelltext abweicht. Sie wird in
§5 als Host-Worklist geführt — **nicht** blind geändert (§8: Philosophie-Familie
gezielt pflegen, nicht auf eine Regel zwingen; §33: Orthoepie-Theorie ist kein Beleg).

---

## 2. Produktionsbug (behoben): die generische `…theorie`-Regel erfand ein Fugen-s

### 2.1 Der Defekt

`app/pronunciation/tech_terms.py`, `_comp()` in der `…theorie`-Suffixregel:

```python
stem = m.group(1)
if stem[-1] not in "nsvtsr":
    stem = stem + "s" if stem[-1] not in "s" else stem   # <-- erfand ein s
repl = f"{stem}-teo-RIE"
```

Der Regex-Capture `([A-Za-zäöüß-]+)theorie\b` enthält ein **echtes** Fugen-s bereits:

| Quellwort | `group(1)` | echtes s im Quellwort |
|---|---|---|
| Informationstheorie | `Informations` | ja |
| Verschwörungstheorie | `Verschwörungs` | ja |
| Feldtheorie | `Feld` | **nein** |

Endete der Stamm nicht auf `n/s/v/t/r`, wurde trotzdem ein `s` angehängt. Der
TTS-Text erhielt dadurch einen **Laut, der im Quellwort nicht vorkommt**:

| Quellwort | vorher (falsch) | nachher |
|---|---|---|
| Feldtheorie | `Felds-teo-RIE` | `Feld-teo-RIE` |
| Musiktheorie | `Musiks-teo-RIE` | `Musik-teo-RIE` |
| Farbtheorie | `Farbs-teo-RIE` | `Farb-teo-RIE` |
| Bildtheorie | `Bilds-teo-RIE` | `Bild-teo-RIE` |
| Netzwerktheorie | `Netzwerks-teo-RIE` | `Netzwerk-teo-RIE` |
| Zelltheorie | `Zells-teo-RIE` | `Zell-teo-RIE` |
| Klimatheorie | `Klimas-teo-RIE` | `Klima-teo-RIE` |
| Sprachtheorie | `Sprachs-teo-RIE` | `Sprach-teo-RIE` |
| Atomtheorie | `Atoms-teo-RIE` | `Atom-teo-RIE` |
| Wärmetheorie | `Wärmes-teo-RIE` | `Wärme-teo-RIE` |

Ausgesprochen wurde also „Felds­theorie", „Musiks­theorie", „Sprachs­theorie".

### 2.2 Warum das ohne Akustik belegt ist

Dies ist derselbe Befund-Typ wie die Kaskaden aus Batch 3: **rein textlich
beweisbar**. Das Buchstaben-Inventar des Outputs wird mit dem des Quellworts
verglichen (erlaubt: die kuratierten Substitutionen `th→t`, `ph→f`,
Umlaut-Umschrift, Bindestriche, Groß/Klein). Ein überschüssiges `s` ist kein
Betonungsurteil und keine Stilfrage, sondern ein Laut ohne Quelle. §33 verbietet
Theorie-als-Beleg für *Betonung* — hier geht es nicht um Betonung.

Symmetrische Inventarprüfung über 43 Komposita:

| | Komposita mit erfundenen Buchstaben |
|---|---|
| vorher | 11 |
| **nachher** | **1** |

Der verbleibende Fall ist `Zahlentheorie → TSAH-len-teo-RIE`: eine **kuratierte**
Regel (`DE_TECH_Zahlentheorie`), die `Z→TS` bewusst setzt. Die generische
Suffixregel greift dort gar nicht (Kaskaden-Guard). Kein Defekt.

### 2.3 Wirkungsumfang — exakt begrenzt

Vorher/Nachher über **alle 312 kuratierten Regeln × 2 Kontexte = 624 Messpunkte**:

| Messung | Ergebnis |
|---|---|
| Kuratierte Regeln verändert | **0 / 624** |
| Komposita-Proben verändert | 10 / 43 (alle: erfundenes `s` entfernt) |
| Testsätze verändert | 3 / 14 |
| 26 Schutzanker (§7/§34) | 26 / 26 intakt |
| Kaskaden-Audit | PASS (0 Kaskaden, 0 Drifts, 0 Isolationsverletzungen) |

Kuratierte Einträge gewinnen weiterhin über den Guard; echte Fugen-s bleiben
erhalten (`Verschwörungs-teo-RIE`, `Kognitions-teo-RIE`, `Regelungs-teo-RIE`).

Der Fix ist 1 Zeile Logik plus Kommentar. Verriegelt durch
`test_theorie_suffix_never_invents_fugen_s()`.

---

## 3. Test-Hygiene-Bug mit Produktionswirkung (behoben)

### 3.1 Der Defekt

`tests/test_phase3.py::test_tech_priority_user_over_tech` rief `clear_all()` und
`add_entry()` auf dem **echten** Benutzer-Wörterbuch auf und räumte nie auf:

```python
d = PronunciationDictionary()
d.clear_all()                                  # loeschte echte Benutzereintraege
d.add_entry("Entropie", "en-tro-PIE-eh")       # blieb dauerhaft stehen
```

**Jeder Lauf der Testsuite löschte damit die echten Benutzereinträge** — konkret
`{"Theorie": "Theorie"}` — und hinterließ dauerhaft `{"Entropie": "en-tro-PIE-eh"}`.

### 3.2 Die Folge war eine reale Produktions-Kaskade

Das Kaskaden-Audit schlug nach einem Suite-Lauf korrekt an:

```
Ergebnis: FINDINGS
- ECHTE Kaskaden: 1
| Entropie | kuratiert: En-tro-PIE | erwartet: En-tro-PIE | tatsächlich: En-tro-PIE-eh |
FINAL_CASCADE_AUDIT=FINDINGS
```

Der kuratierte Wert `Entropie → En-tro-PIE` wurde vom Benutzer-Layer auf
`En-tro-PIE-eh` überschrieben. Das ist kein Test-Artefakt: Die Datei liegt im
Repo-Pfad und wird von der Produktion gelesen. Ein Testlauf veränderte also das
tatsächliche Aussprache-Ergebnis.

### 3.3 Behebung

- `pronunciation/pronunciation.json` auf den Commit-Stand zurückgesetzt
  (`{"Theorie": "Theorie"}`, byte-identisch, mit abschließendem Zeilenumbruch).
- Der Test läuft jetzt gegen eine **Temp-Datei** (`paths.PRONUNCIATION_FILE`
  umgebogen, `finally` stellt Pfad und Inhalt wieder her, Temp-Datei wird gelöscht).
- Neuer Guard `test_suite_does_not_pollute_user_dictionary()` verriegelt das
  Fixture-Leck dauerhaft.

Nachweis: Test 3× ausgeführt, Wörterbuch jedes Mal unverändert; danach komplette
Suite gelaufen — `pronunciation/pronunciation.json` bleibt byte-identisch;
Audit wieder **PASS**, auch `Pass-2-Drifts` wieder 0.

---

## 4. Zwei veraltete Tests korrigiert

Beide waren bereits auf dem Ursprungs-Commit `348e45d` rot — sie widersprachen
Entscheidungen, die das Projekt später getroffen hat. Der Code war richtig, die
Tests waren alt.

**4.1 `test_tech_terms_user_reported`** verlangte, dass auch das freistehende
„Theorie" zu `teo-RIE` wird. Das widerspricht dem geschützten Anker aus §7/§34:
„Theorie" ist host-verifiziert gut und steht als Identity in `TECH_TERMS_DE`.
Assertion jetzt: das Kompositum wird umgeschrieben, die Grundform bleibt Identity.

**4.2 `test_tech_suffix_rule_for_compounds`** erwartete die Regel-ID
`tech_suffix`; emittiert wird seit der Namespace-Einführung
`DE_TECH_suffix_theorie`. Erwartung auf den tatsächlichen Namen gestellt.

---

## 5. Host-Worklist: was der Qwen-Lauf klären muss

Diese Befunde sind **textlich dokumentiert, aber nicht akustisch entschieden**.
Sie werden bewusst nicht in die Produktion übernommen, bevor der Host-Lauf
gehört ist (§8, §33). Jede Zeile ist als Variante C im Harness hinterlegt.

| Begriff | aktuelle Regel | Befund-Klasse | Variante C |
|---|---|---|---|
| Philosoph | `FI-lo-sof` | Wert widerspricht dem eigenen Code-Kommentar („Phi-lo-SOF") **und** dem Geschwister `Philosophen → fi-lo-ZO-fen` (3. Silbe) | `fi-lo-ZOF` |
| Philosophinnen | `fi-lo-zo-FIN-nen` | Plural betont 4. Silbe, Singular `Philosophin → fi-lo-ZO-fin` betont 3.; `-nen` verschiebt im Deutschen die Betonung nicht | `fi-lo-ZO-fin-nen` |
| Software | `SORFT-wär` | Das `R` kommt im Quellwort nicht vor; Geschwister `HARD-wär`, `FIRM-wär`, `MID-del-wär` behalten den Cluster korrekt | `SOFT-wär` |
| Physik | `FY-sik` | Betonung auf Silbe 1, Geschwister `fy-SI-sch`, `A-stro-fy-SIK`, `Kern-fy-SIK` betonen später | *(nur A/B)* |

Zusätzlich Bestandsaufnahme: **7 Respell-Einträge ohne Betonungsmarkierung**
(Inventory im Audit, keine Wertung).

---

## 6. A/B-Harness (neu): `tools/test_pronunciation_ab.py`

Familienweiser Blindvergleich, gebaut um den Konfundierungseffekt zu beseitigen,
den ein termweiser Ansatz hätte: Steht in einem Satz sowohl „Philosoph" als auch
„Philosophie", würde das Umschalten nur *einer* Regel die andere umgeschrieben
lassen — der Vergleich wäre wertlos. Deshalb werden Varianten **pro Familie**
erzeugt, und alle Mitglieder einer Familie werden gemeinsam umgestellt
(`family_overrides()`, `family_units()`).

- **A** = aktueller Produktionszustand
- **B** = Identity (natürliche Orthographie)
- **C** = minimale Alternative, nur wo eine begründete Form hinterlegt ist
  (derzeit Philosoph, Philosophinnen, Software)

Blind-Randomisierung über `--seed`; Ausgabe = WAVs + `worksheet.md` + `key.json`
+ `results.json` nach `output/pronunciation_ab/`.

| Aufruf | Begriffe | Familien | Clips |
|---|---|---|---|
| `--dry-run` (Prioritätenliste) | 61 | 14 | 58 |
| `--dry-run --all-respells` (Voll-Sweep) | 262 | 213 | 818 |

818 Clips = A 407 / B 407 / C 4, bei 2 Trägersätzen pro Familie. Beide
DE-Regressionsstimmen (`de_male_warm_storytelling_authoritative_01`,
`de_male_warm_calm_authoritative_02`) → **1636 Synthesen**. Eine Laufzeit wird
hier nicht angegeben: im Repo ist keine gemessene Rate pro Clip hinterlegt, und
eine geschätzte Zahl wäre erfunden.

```bash
cd project
python tools/test_pronunciation_ab.py --dry-run          # Plan offline pruefen
python tools/test_pronunciation_ab.py --only Philosoph   # Familie gezielt
python tools/test_pronunciation_ab.py --limit 20         # gestaffelt
python tools/test_pronunciation_ab.py                    # Prioritaetsliste, GPU
python tools/test_pronunciation_ab.py --all-respells     # Voll-Sweep, GPU
```

Das Tool schreibt nachweislich nicht in `pronunciation/pronunciation.json`
(Override nur im Speicher; verriegelt durch
`test_user_dictionary_file_untouched_by_ab_tooling`).

---

## 7. Testausbau

`tests/test_pronunciation_cascade.py`: 19 → **23 Tests**, alle grün.

| Test | Zweck |
|---|---|
| `test_user_reported_families_are_natural` | 10 Familien × mehrere Formen × Satzkontexte bleiben natürliche Orthographie |
| `test_no_confirmed_bad_form_ever_reaches_tts` | 22 historisch als schlecht bestätigte Formen dürfen nie wieder an das TTS gelangen |
| `test_philosoph_family_state_is_pinned` | pinnt den Philosoph-Ist-Zustand, bis der Host A/B entschieden hat |
| `test_user_dictionary_file_untouched_by_ab_tooling` | A/B-Tooling fasst `pronunciation.json` nicht an |

`tests/test_phase3.py`: `test_theorie_suffix_never_invents_fugen_s` (10 No-s-Formen
+ 7 Echt-s-Formen + 10 kuratierte Guard-Fälle) und
`test_suite_does_not_pollute_user_dictionary`.

### Audit-Tooling

`tools/pronunciation_cascade_audit.py` erhielt `objective_worklist()` mit
`DOCUMENTED_TEXT_FINDINGS` (die 3 manuell verifizierten Befunde aus §5) und
`no_stress_marker()` (Bestandsaufnahme).

**Drei heuristische Detektoren wurden gebaut und wieder entfernt** — sie waren zu
rauschbehaftet und wären irreführend gewesen:

- `unexplained_fragment` (Buchstaben-Inventar-Delta): 42/262 Treffer, überwiegend
  legitim (Dehnungs-h, `ph→f`, Umlaut-Expansion).
- `family_stress_divergence`: 16 Treffer, aber Betonungsverschiebung innerhalb
  einer Familie ist normales Deutsch (`Algebra → AL-ge-bra` vs.
  `algebraisch → al-ge-BRA-isch`).
- `comment_value_contradictions`: 67 Treffer, fast alles deutsche Komposita im
  Fließtext der Kommentare; Kommentare referenzieren zudem absichtlich
  *historisch entfernte* Formen (`A-TOM-kern`, `be-WUSST-sein`, `Pro-TO-nen`).

Lehre: verlässlich sind nur manuell verifizierte, einzeln dokumentierte Befunde.
Ausgeliefert werden explizite Tabellen, keine Heuristiken.

---

## 8. Verifikation

| Prüfung | Ergebnis |
|---|---|
| Vollständige Testsuite | **83/135 bestanden, 57 fehlgeschlagen** |
| …davon pronunciation-bezogen | **0** |
| Restfehler-Ursachen | 36× `No module named 'numpy'`, 5× Modul-Import, 4× fehlende Datei, 1× Server, 1× Connection refused — reine Sandbox-Umgebung, kein GPU/torch/numpy |
| Vorher-Nachher | Ursprung `348e45d`: 75/129, 59 Fehler → Vorrunde `809818c`: 79/133, 59 → **jetzt 83/135, 57** |
| Cascade-Suite | 23/23 |
| 26 Schutzanker (§7/§34) | 26/26 intakt (Isolation + Satz + kuratierter Wert) |
| Kaskaden-Audit | **PASS** — 312 Regeln, 0 echte Kaskaden, 0 Kontext-Drifts, 0 Pass-2-Drifts, 0 DE/EN-Isolationsverletzungen |
| DE/EN-Isolation | EN-Pfad 5/5 no-op; `Thriller`, `Workflow`, `Service` bleiben im DE-Gemischtext unangetastet |
| `pronunciation/pronunciation.json` | byte-identisch zum Commit-Stand, auch nach kompletter Suite |
| Golden Reference (§4) | `b156c02a60a873ad95fc92390c4a136c85308b20188373cd734bee5e5e5f2025` — **beide** Pfade, nur lesend geprüft |

Bestandsaufnahme Audit: 292 Begriffe im Katalog, 69 Identity, 57 aktive
Respell-Regeln (Host-Testkandidaten), 166 ohne Regel (natürliche Lesart).

---

## 9. Bewusst NICHT geändert

| Was | Warum nicht |
|---|---|
| Philosoph, Philosophinnen, Software, Physik | Textbefund dokumentiert, aber §8 verlangt für die Philosophie-Familie gezielte Prüfung statt einer erzwungenen Regel; §33 verbietet Theorie als Beleg. Geht als Variante C in den Host-Lauf. |
| Daten, Prozessor, Matrix, Erkenntnis, Logarithmus, Vektor, Gleichung, Quellcode, Metaphysik, Ontologie | Liefern bereits natürliche Orthographie (§1). Es gibt nichts zu korrigieren. |
| `engine.py` | Unverändert; Pass 1 bleibt case-insensitiv, Tie-Break `(-len(t), t[:1].isupper())`. |
| `_effective_map._put()` / `set_tech_layer()` | Format-Mismatch bleibt dokumentiert + wächtergesichert, nicht „repariert": Aktivieren würde 301 Begriffe in einem zweiten Durchlauf ersetzen und genau die Kaskaden öffnen, die der Guard ausschließt. |
| GUI, Presets, Pausen-/Assembly-Logik, Prosodie, Stimmen-Bundles | Abgeschlossen, nicht berührt. |
| 24 wertidentische Doppel-Keys | Kosmetik; 0 Wert-Konflikte. |
| Betonungspositionen nach orthoepischer Theorie | Explizit kein zulässiger Beleg (§33). |

---

## 10. Geänderte Dateien

**Produktion (1 Datei):**

- `project/app/pronunciation/tech_terms.py` — `_comp()`: erfundenes Fugen-s
  entfernt (+19/−2 Zeilen, davon der Großteil Kommentar). Keine Regelwerte geändert.

**Tests (2 Dateien):**

- `project/tests/test_phase3.py` — 2 veraltete Tests korrigiert,
  Wörterbuch-Test isoliert, 2 Tests neu
- `project/tests/test_pronunciation_cascade.py` — 19 → 23 Tests

**Tools (2 Dateien):**

- `project/tools/test_pronunciation_ab.py` — neu, familienweiser A/B/C-Blindvergleich
- `project/tools/pronunciation_cascade_audit.py` — `objective_worklist()`,
  Heuristiken entfernt

**Bericht:** `project/PRONUNCIATION_BATCH4_REPORT.md` (diese Datei)

**Wiederhergestellt:** `project/pronunciation/pronunciation.json` (war durch den
Testlauf auf `{"Entropie": "en-tro-PIE-eh"}` verstellt)

**Nicht berührt:** GUI, Presets, Pausen-/Assembly-Logik, Prosodie, TTS-Engine,
Golden Reference, Stimmen-Bundles, `engine.py`, `dictionary.py`.

---

## 11. Nächste Schritte (Host, RTX 5060)

1. **A/B-Lauf der Prioritätenliste** (58 Clips, 14 Familien, 2 Stimmen):
   ```bash
   cd project && python tools/test_pronunciation_ab.py
   ```
   Erste Entscheidung: Philosoph-Familie — gewinnt A (`FI-lo-sof`), B (Identity)
   oder C (`fi-lo-ZOF`)? Und: `Software` → `SORFT-wär` oder `SOFT-wär`?
2. Gehörte Ergebnisse in `output/pronunciation_ab/results.json` eintragen;
   **nur bestätigte** Verlierer minimal ändern, dann §7/§34-Anker + Audit neu fahren.
3. Optional Voll-Sweep (`--all-respells`, 818 Clips / 1636 Synthesen) für die
   übrigen 57 Respell-Kandidaten — gestaffelt mit `--limit N`.
4. Der Fugen-s-Fix (§2) ist textlich belegt und braucht keinen Host-Lauf;
   er ist mit dieser Runde übernommen. Ein Hören von `Feld-theo-RIE` vs.
   `Felds-teo-RIE` bleibt als Stichprobe möglich.

---

## 12. Folgerunde (Batch 5, 2026-09-23) — ABSCHLUSSRUNDE

Mit echten Qwen-Hörbefunden des Nutzers (§4: „B ist bei Teilchenphysik und
Thermodynamik besser als A", „B ist bei Software gut", „C ist insgesamt
schlechter als B") lagen erstmals akustische Belege vor. Fünf Begriffe wurden
daraufhin **produktiv** auf Identity übernommen:

`Teilchenphysik`, `Thermodynamik`, `Software`, `Analysis`, `Elementarteilchen`

Offen bleiben `Wellenlänge` (neue Variante C `WEL-len-länge` bereitgestellt),
`Energie` (Ursache der gehörten Inkonsistenz objektiv geklärt: die Regel greift
nur an Wortgrenzen, in Komposita nie) und die `Philosoph`-Familie
(dokumentiertes Gegenrisiko: englisches /f aɪ/ „fie" ohne Respell).

Suite 83/135 → **87/139**, Cascade-Suite 23 → **27 Tests**, Anker 26/26,
Audit **PASS**, Golden Reference unverändert.

Eigenständiger Bericht: **`PRONUNCIATION_BATCH5_REPORT.md`**
