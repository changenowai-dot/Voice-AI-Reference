# VoiceOverApp — Fachwort-Batch 3: Kaskaden-Forensik & Minimal-Korrektur

**Datum:** 2026-09-23
**Teil:** A (GitHub / `Voice-AI-Reference`) — kein Teil-B-, kein Master-LIVE-Code
**Basis-Commit:** `348e45d00f3985dbccf45a3c12d0f34fa398cbc8`
**Leitgedanke:** sehr großer Testumfang · Identity first · minimale Korrekturen · maximaler Regressionsschutz

---

## 0. Vorab: Zweig und Host-Umgebung

**Branch.** Diese Sitzung ist fest auf `arena/01a0ce4d-voice-ai-reference` gebunden,
abgezweigt von `348e45d` (= zum Zeitpunkt der Übernahme der tatsächliche
Remote-HEAD von `arena/01a08d48-voice-ai-reference`, per `git ls-remote` verifiziert).
Der in der Übergabe genannte SHA `2ebf0aab…` war **nicht** mehr aktuell; gearbeitet
wurde auf dem verifizierten Stand `348e45d`. Inhaltlich ist das derselbe Teil-A-Stand.

**Kein echter Qwen-Test möglich.** Die Sandbox hat keine GPU:

| Voraussetzung | Status |
|---|---|
| CUDA / `nvidia-smi` | nicht vorhanden |
| `torch` | nicht installiert |
| `soundfile` | nicht installiert |
| `numpy` | nicht installiert |

`tools/test_pronunciation_tts.py --skip-if-no-gpu` meldet deshalb sauber
`SKIP (torch/CUDA nicht verfügbar)` mit Exit-Code 0.

**Konsequenz für die Arbeitsweise (§31/§33).** Es wurde **keine** Regel aufgrund
einer akustischen Vermutung geändert. Geändert wurde ausschließlich, was
**rein textlich beweisbar** falsch war — also Fälle, in denen der TTS-Text
objektiv nicht dem kuratierten Wert entsprach. Für alles Akustische wurde die
Host-Teststruktur ausgebaut und eine priorisierte Worklist hinterlegt (§7).

---

## 1. Kernbefund: drei echte Kaskaden (§5.2-Mechanismus, noch live)

Der in der Übergabe dokumentierte Mechanismus (`A-TOM-kern` → `A-TOM-KERN`) war
**nicht** mit den Atom-Fixes verschwunden. Er lebte in drei anderen Regeln weiter.
Künstliche Bindestriche erzeugen neue Wortgrenzen; die Ersetzungsschleife lief über
den jeweils bereits umgeschriebenen Text, wodurch kurze Teilwort-Regeln die Outputs
längerer Regeln still überschrieben.

| Begriff | Kuratiert (Absicht) | Tatsächlich an Qwen übergeben | Auslöser |
|---|---|---|---|
| `Kinematik` | `Ki-ne-MA-tik` | **`K I-ne-MA-tik`** | `KI → "K I"` |
| `Kernphysik` | `Kern-fy-SIK` | **`KERN-fy-SIK`** | `Kern → KERN` |
| `Regelungstechnik` | `RE-ge-lungs-technik` | **`RE-ge-lungs-TECH-nik`** | `Technik → TECH-nik` |

`Kinematik` ist der schwerste Fall: ein **buchstabiertes Akronym mitten im Wort**.
Der Satz „Die Kinematik beschreibt Bewegungen von Körpern." ging als
„Die **K I**-ne-MA-tik beschreibt Bewegungen von Körpern." an das TTS-Modell.
Das ist unabhängig von jeder Akustik objektiv falsch — deshalb ist der Beleg hier
auch ohne GPU-Hosttest tragfähig im Sinne von §33.

Diese drei Begriffe standen **nicht** in der Kandidatenliste der Übergabe (§20).
`Kernphysik` fiel dort nur indirekt als Beobachtung `KERN-fy-SIK` auf — die
Ursache (Kaskade, nicht Kuratierung) war bisher nicht identifiziert.

### §21 aufgelöst (war als offener Punkt übergeben)

Die befürchtete zweistufige Kaskade `neuronales Netzwerk → neuronales NETZ-werk →
Neuro-NA-les Netz-werk` **tritt nicht ein**. Deterministisch nachgewiesen:

```
Ein neuronales Netzwerk lernt aus Beispielen.
→ Ein neuronales NETZ-werk lernt aus Beispielen.
```

`Neuronales Netz` kann in `Netzwerk` nicht matchen, weil sein Lookahead hinter
`Netz` eine Wortgrenze verlangt und dort `w` steht. Es gibt also **nur eine**
Stufe, verursacht von der regulären `Netzwerk`-Regel. §21 verlangte „zuerst
echten Qwen-Hosttest/A-B" — der ist für die Aussprache von `NETZ-werk` weiterhin
offen, die **Kaskaden-Frage** selbst ist damit aber beantwortet und braucht keinen
Hostlauf mehr.

---

## 2. Weitere deterministische Befunde

### 2.1 Wert-Konflikt durch doppelten Key

`Thermodynamik` stand **zweimal** mit **unterschiedlichem** Wert:

| Zeile | Wert | Status |
|---|---|---|
| 61 | `Thermo-dy-NA-mik` | toter Code |
| 240 | `Ther-mo-dy-NA-mik` | gewinnt (Python: letzter Key) |

In einem `dict`-Literal gewinnt der letzte Key still. Der erste Eintrag ist
unerreichbarer Code und eine latente Fehlerquelle: Wer Zeile 61 „korrigiert",
ändert akustisch nichts. **Entfernt wurde der inaktive Eintrag** — das Verhalten
bleibt bit-identisch, es wurde keine Aussprache angefasst.

Insgesamt: 25 doppelte Keys, davon **1** mit Wert-Konflikt. Die übrigen 24 sind
wertidentisch und wurden bewusst nicht angefasst (§30: wenig ändern).

### 2.2 Redundante Case-Varianten

`Mathematische` und `Logarithmisch` sind gleichlange Case-Varianten ihrer
Klein-Keys. Bei gleicher Länge entschied die Insertion-Reihenfolge — zusammen mit
dem Kaskaden-Guard hätte die GROSS-Variante endgültig gewonnen:

```
Die mathematische Analyse …   →   Die Mathematische Analyse …   ✗
```

Das wäre eine **Regression am §7-Anker `mathematische`** gewesen. Beide
Groß-Duplikate wurden entfernt; die Klein-Keys matchen case-insensitiv und
capitalisieren am Satzanfang korrekt. Zusätzlich wurde ein **deterministischer
Tie-Break** (`t[:1].isupper()`) eingeführt, damit gleichlange Case-Varianten nie
wieder von der Dict-Reihenfolge abhängen.

### 2.3 WÄCHTER-Befund: der Dictionary-Tech-Layer ist inert

`PronunciationEngine.__init__` registriert die Tech-Map **zusätzlich** im
Wörterbuch (`set_tech_layer`), `process()` wendet sie danach über
`apply_to_text` ein zweites Mal an. Dieser zweite Durchlauf ist jedoch
**wirkungslos**:

`set_tech_layer()` erzeugt `{"repl": …}`, `_effective_map._put()` liest aber
`value.get("de")` bzw. `value.get("en")` → `repl = None` → jeder Eintrag wird
verworfen.

```
_tech_layer gesetzt:        312 Begriffe
im effective map wirksam:     0 von 301 tech-only Begriffen
```

**Das wurde bewusst NICHT „repariert".** Eine Aktivierung würde 301 Begriffe in
einem **zweiten** Durchlauf ersetzen und genau die Re-Durchlauf-Kaskaden wieder
öffnen, die §5.2 verbietet. Der Status quo — **ein** Durchlauf, deterministisch —
ist der sichere Zustand. Er ist jetzt durch einen Wächter-Test fixiert
(`test_tech_layer_stays_inert_in_dictionary_pass`), der anschlägt, sobald jemand
`_put()` ändert.

### 2.4 Akronym-Keys sind bereits vorgelagert erledigt

`normalize_text` buchstabiert `KI`, `DNA`, `RNA`, `GPU`, `CPU`, `TPU`, `DNS`,
`RNS`, `K.I.` **vor** der Fachwort-Schicht. Die entsprechenden Einträge in
`TECH_TERMS_DE` sind damit redundant (11 Begriffe, im Audit als
`normalized-before-tech` gekennzeichnet, kein Befund).
Nur deshalb konnte `KI` überhaupt in `Ki-ne-MA-tik` greifen: die Regel feuerte
nicht auf das Akronym im Text, sondern auf das Fragment eines Respell-Outputs.

### 2.5 DE/EN-Isolation (§14) — bestätigt

0 Verletzungen. 5 englische Probesätze durchlaufen den Pfad mit `language="English"`
und bleiben zeichenidentisch; keine `DE_TECH_*`-Regel feuert.

---

## 3. Änderungen an Produktionsregeln

**Geändert: 4 Begriffe.** Unverändert: 308 Regeln.

| Begriff | Vorher | Nachher | Beleg | Geändert? |
|---|---|---|---|---|
| `Kinematik` | `Ki-ne-MA-tik` → lieferte `K I-ne-MA-tik` | `Ki-ne-MA-tik` (wie kuratiert) | Kaskade, textlich bewiesen | **ja** (Mechanismus) |
| `Kernphysik` | `Kern-fy-SIK` → lieferte `KERN-fy-SIK` | `Kern-fy-SIK` (wie kuratiert) | Kaskade, textlich bewiesen | **ja** (Mechanismus) |
| `Regelungstechnik` | `RE-ge-lungs-technik` → lieferte `RE-ge-lungs-TECH-nik` | `RE-ge-lungs-technik` (wie kuratiert) | Kaskade, textlich bewiesen | **ja** (Mechanismus) |
| `Mikroprozessor` | `Mi-kro-pro-TS-ess-sor` | `Mikroprozessor` (Identity) | User-Hörbefund §19 für `Prozessor`, identischer Cluster; §24 Begriffsfamilie | **ja** (Regelwert) |

Wichtig zur Einordnung: Bei den ersten drei wurde **keine Aussprache neu
festgelegt**. Der kuratierte Wert stand bereits in `TECH_TERMS_DE` und kam nur
nie an. Der Kaskaden-Guard sorgt dafür, dass das Kuratierungsergebnis jetzt das
Endergebnis ist.

`Mikroprozessor` ist die **einzige** Regelwert-Änderung. Sie ist direkt aus dem
bestätigten User-Hörbefund abgeleitet: `Prozessor` wurde als problematisch
gemeldet, die aktive Form war `Pro-TS-ess-sor`, und sie steht inzwischen auf
Identity. `Mikroprozessor` trug exakt denselben Cluster `pro-TS-ess-sor` weiter.
Nach §32 (Identity, wenn die aktuelle Form schlecht klingt und Identity gut) und
§24 (Begriffsfamilien prüfen) ist das Family-Konsistenz, keine neue Erfindung.

### Bewusst NICHT geändert

| Begriff | Aktuelle Form | Grund |
|---|---|---|
| `Philosoph`-Familie | `FI-lo-sof`, `fi-lo-ZO-fen`, `fi-lo-zo-FIE` | §19: „Hörbefund vorsichtiger formuliert, daher zuerst verifizieren". Ohne GPU nicht verifizierbar → keine Änderung (§33). **Prio 1 für den Hostlauf.** |
| `Energie` | `E-NER-gie` | §22: ausdrücklich kein bestätigter Hörbefund. Unverändert gelassen. |
| `Thermodynamik` | `Ther-mo-dy-NA-mik` | Nur der tote Duplikat-Eintrag entfernt; aktive Aussprache unangetastet. |
| übrige 53 Respell-Kandidaten | — | Nur Kandidaten, kein Gegenbeleg. §20: „OFFLINE-KLASSIFIZIERUNG ≠ akustischer Beweis". |
| 24 wertidentische Doppel-Keys | — | Kosmetik, kein Nutzen, nur Risiko (§30). |
| GUI / Presets / Pausen / Prosodie | — | §35: abgeschlossen, nicht berührt. **0 Zeilen geändert.** |

---

## 4. Verifikation

### 4.1 Vollständiger Vorher-/Nachher-Diff über alle Regeln

Alle 314 Regeln × 3 Kontexte (isoliert, im Trägersatz, kleingeschrieben) = **942
Messpunkte** plus 19 natürliche Sätze, jeweils vor und nach der Änderung über den
**realen Produktionspfad** (`normalize_text` + `PronunciationEngine.process`).

```
Veränderte Kontexte:  12 von 942
Betroffene Begriffe:   4  (Kernphysik, Kinematik, Regelungstechnik, Mikroprozessor)
Veränderte Sätze:      4 von 19
```

Alle 12 Änderungen sind die vier beabsichtigten Begriffe — **nichts sonst**.

### 4.2 Regressionsanker (§7/§34)

Alle **26 Anker** in allen 3 Kontexten: **bit-identisch**, 0 Diffs.

```
Atom · Atome · Atomkern · Zelle · Zellen · Proton · Protonen · Neutron ·
Neutronen · Mathematik · mathematisch · mathematische · mathematischen ·
mathematischer · mathematischem · Algorithmus · Algorithmen · Quantenphysik ·
Quantenmechanik · Neurowissenschaft · Statistik · Psychologie · psychologisch ·
Theorie · Wahrscheinlichkeit · Bewusstsein
```

Zusätzlich explizit als Test fixiert: `Bewusstsein` enthält nie wieder
`be-WUSST-sein` (§8), die Teilchenfamilie enthält nie wieder
`Pro-TO-nen`/`Noi-tro-NEN`/`E-lek-TRON` (§10).

### 4.3 Bestehende Testsuite — keine Regression

Vollständiger Lauf, Original-Stand vs. neuer Stand, Fehlermengen verglichen:

| | Original `348e45d` | Nach Änderung |
|---|---|---|
| Tests gesamt | 110 | 129 (+19 neue) |
| bestanden | 56 | **75** |
| fehlgeschlagen | 59 | **59** |

```
NEU fehlerhaft (Regression):  keine
Fehlermengen:                 bit-identisch
```

Alle 59 Fehler sind **vorbestehende Umgebungsfehler** dieser Sandbox ohne GPU:
36 × `No module named 'numpy'`, 5 × Modul-Import (numpy-Kette), 4 × fehlende
Packaging-Dateien (`VoiceOverApp.spec`/`.bat`), 1 × Server, 1 × Connection refused.
Sie bestehen auf dem Original-Commit exakt gleich.

Pronunciation-relevante Module isoliert: **35/35 bestanden**.

### 4.4 Kaskaden-Audit

```
FINAL_CASCADE_AUDIT=PASS

geprüfte Regeln:                     312
ECHTE Kaskaden:                        0   (vorher 3)
Wert-Konflikte:                        0   (vorher 1)
Pass-2-Drifts:                         0
DE/EN-Isolationsverletzungen:          0
erklaerte Zustaende (kein Befund):    11
latente Paare (nur falls Pass 2 aktiv): 2
```

### 4.5 Golden Reference (§4) — nur lesend geprüft

```
project/VD-E_GOLDEN_REFERENCE/VD-E.wav
  b156c02a60a873ad95fc92390c4a136c85308b20188373cd734bee5e5e5f2025   ✓
reference/VD-E_GOLDEN_REFERENCE/VD-E.wav
  b156c02a60a873ad95fc92390c4a136c85308b20188373cd734bee5e5e5f2025   ✓
erwartet
  B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025   ✓
```

Vor und nach allen Änderungen identisch. `git status` für beide Pfade: leer
(Dateien nicht modifiziert, nicht neu erzeugt).

---

## 5. Testinfrastruktur ausgebaut

`tools/test_pronunciation_tts.py` (echter Qwen, GPU-Host) wurde erweitert, die
vorhandene Struktur und `--limit`-Staffelung bleiben unverändert:

| | vorher | nachher |
|---|---|---|
| `REGRESSION_SENTENCES` | 72 | **134** |
| Synthesen pro Lauf (2 DE-Stimmen) | 116 → (mit Stafflung) | 268 |
| Katalog-Begriffe **ohne** Satz-Coverage | 127 | **0** |

Alle **292 Katalog-Begriffe** aus §24–§29 sind jetzt in natürlichen Sätzen
abgedeckt. Batch 3 ist in drei Blöcke gegliedert:

- **3a** — die drei Kaskaden-Opfer (`Kinematik`, `Kernphysik` war schon da,
  `Regelungstechnik`, `Mikroprozessor`)
- **3b** — Begriffsfamilien der User-Hörbefunde (§24)
- **3c** — Katalog-Lücken Physik/Chemie/Biologie/Astronomie/Mathe/Informatik/
  Neuro/Philosophie (§25–§29)

Die Sätze sind bewusst natürlich formuliert (kein Keyword-Stuffing), da nur
realistischer Voiceover-Text eine akustische Beurteilung erlaubt.

Alle 134 Sätze wurden offline durch den Produktionspfad geschickt:
**0 Kaskaden-Muster, 0 Platzhalter-Lecks**.

Empfohlene gestaffelte Host-Läufe:

```bash
python tools/test_pronunciation_tts.py --limit 20     # Anker + Teilchenfamilie
python tools/test_pronunciation_tts.py --limit 73     # bisheriger Stand + Batch-3a
python tools/test_pronunciation_tts.py                # alle 134 × 2 Stimmen
```

---

## 6. Neue Dateien

| Datei | Zweck |
|---|---|
| `project/tools/pronunciation_cascade_audit.py` | Deterministisches Offline-Audit: Kaskaden, doppelte Keys/Wert-Konflikte (AST), Pass-2-Drift, Wächter „Tech-Layer inert", DE/EN-Isolation, Katalog-Coverage. Schreibt JSON + Markdown, Exit-Code CI-fähig. Braucht **keine GPU**. |
| `project/tests/test_pronunciation_cascade.py` | 19 Regressionstests: Kaskaden-Guard, alle 26 Anker, `Bewusstsein`/Teilchenfamilie, §21-Auflösung, Prozessor-Familie, Wert-Konflikt-Lint, Case-Varianten-Tie-Break, Inert-Wächter, DE/EN-Isolation, Platzhalter-Leck. Läuft in ~4 s. |

Beide sind Offline-Werkzeuge und Teil der regulären Suite (`tests/run_all.py`
findet `test_*.py` automatisch).

---

## 7. Host-Worklist: was der Qwen-Lauf klären muss

Diese Begriffe sind **nicht** geändert worden, weil ohne echten Qwen kein Beleg
möglich ist. Reihenfolge = Priorität.

**Prio 1 — User-Hörbefund §19, noch offen (Philosoph-Familie, 5 Regeln)**

| Begriff | Aktuelle Form | Zu prüfen |
|---|---|---|
| `Philosoph` | `FI-lo-sof` | Identity `Philosoph` A/B |
| `Philosophen` | `fi-lo-ZO-fen` | Identity A/B |
| `Philosophin` | `fi-lo-ZO-fin` | Identity A/B |
| `Philosophie` | `fi-lo-zo-FIE` | Identity A/B |
| `philosophisch` | `fi-lo-ZO-fisch` | Identity A/B |

Hinweis: Die Familie ist **intern inkonsistent** — `Philosophie` endet auf `-FIE`,
`Philosoph` auf `-sof`. Der Code-Kommentar begründet `-sof` damit, dass Qwen für
`phie` das englische /faɪ/ erzeuge; `fi-lo-zo-FIE` behält aber genau dieses `FIE`.
Das ist ein Widerspruch in der Kuratierung, aber **kein** textlich beweisbarer
Fehler → nicht angefasst. Der Hostlauf sollte beide Endungen getrennt hören.

**Prio 2 — Kaskaden-Fixes akustisch bestätigen (3 Regeln).** Der Textfehler ist
behoben; zu hören ist nur noch, ob die jetzt tatsächlich übergebene Form
(`Ki-ne-MA-tik`, `Kern-fy-SIK`, `RE-ge-lungs-technik`) gut klingt — oder ob auch
hier Identity besser wäre.

**Prio 3 — übrige aktive Respell-Regeln: 57 Kandidaten**

| Kategorie | Anzahl | Begriffe |
|---|---|---|
| Physik | 19 | Photon, Photonen, Wellenlänge, Frequenz, Energie, Entropie, Temperatur, Teilchenphysik, Elementarteilchen, Kernphysik, Elektrizität, Spannung, Widerstand, Beschleunigung, Gravitation, Relativitätstheorie, Thermodynamik, Impuls, Quantenfeldtheorie |
| Mathematik/Statistik | 11 | Algebra, Geometrie, Analysis, Integral, Integrale, Ableitung, Variable, Variablen, Funktion, Funktionen, Exponentialfunktion |
| Philosophie | 6 | Philosoph, Philosophen, Philosophie, philosophisch, Determinismus, Epistemologie |
| Chemie | 4 | Molekül, Moleküle, Chemie, chemisch |
| Informatik/Technik | 4 | Software, Hardware, Netzwerk, Netzwerke |
| Neuro/Psychologie | 4 | Neurotransmitter, Neuroplastizität, Kognition, kognitiv |
| Biologie | 2 | Genetik, Organismus |
| Astronomie | 2 | Astronomie, astronomisch |

(Doppelnennungen über Kategorien sind möglich; `Energie` bleibt per §22
ausdrücklich unverändert, solange kein Hörbefund vorliegt.)

---

## 8. Kennzahlen (§39)

| Kennzahl | Wert |
|---|---|
| Geprüfte Produktionsregeln | **312** (vorher 314; −1 toter Konflikt, −2 redundante Case-Varianten) |
| Katalog-Begriffe (Audit) | **292** in **10** Kategorien |
| davon Identity | 69 |
| davon aktive Respell-Regeln (Host-Kandidaten) | **57** |
| davon ohne Regel (natürliche Lesart) | 166 |
| Messpunkte Vorher/Nachher | **942** Term-Kontexte + 19 Sätze |
| Echte Kaskaden gefunden | **3** |
| Kaskaden behoben | **3** |
| Wert-Konflikte gefunden / behoben | **1 / 1** |
| Begriffe geändert | **4** |
| Begriffe unverändert gelassen | **308** |
| Regressionsanker geprüft | **26**, alle bit-identisch |
| Host-Testsätze | 72 → **134** (+62) |
| Echte Qwen-Synthesen in dieser Sitzung | **0** (keine GPU in der Sandbox) |
| Offline-Regressionstests | **19** neu, alle grün |
| Bestehende Suite | 59 Fehler vorher = 59 nachher, **bit-identisch** |
| Golden Reference SHA | `b156c02a…5f2025` ✓ unverändert |

---

## 9. Geänderte Dateien

**Produktion (2 Dateien, Aussprache-Verhalten nur wie in §3 beschrieben):**

- `project/app/pronunciation/tech_terms.py` — Kaskaden-Guard (Maskierung +
  Auflösung nach der Suffix-Stufe), deterministischer Tie-Break, 1 toter
  Wert-Konflikt entfernt, 2 redundante Case-Varianten entfernt,
  `Mikroprozessor` → Identity
- `project/app/pronunciation/dictionary.py` — **nur Docstring**: Befund
  „Tech-Layer inert" dokumentiert, kein Code-Pfad geändert

**Test/Tooling (3 Dateien):**

- `project/tools/test_pronunciation_tts.py` — +62 Host-Sätze (Batch 3a/3b/3c)
- `project/tools/pronunciation_cascade_audit.py` — neu
- `project/tests/test_pronunciation_cascade.py` — neu

**Nicht berührt:** GUI, Presets, Pausen-/Assembly-Logik, Prosodie, TTS-Engine,
Golden Reference, Stimmen-Bundles, `engine.py` (nach Rücknahme einer
Zwischenstufe wieder byte-identisch zum Original).

---

## 10. Offene Punkte für die nächste Sitzung

1. **Hostlauf auf der RTX 5060** mit `tools/test_pronunciation_tts.py`
   (134 Sätze × 2 Stimmen). Prio 1 = Philosoph-Familie.
2. Die 57 Respell-Kandidaten nach Gehör triagieren: Identity first, nur bei
   echtem Gegenbeleg minimale Alternative.
3. Optional: die 24 wertidentischen Doppel-Keys deduplizieren (Kosmetik,
   verhindert künftige Wert-Konflikte wie bei `Thermodynamik`).
4. `_effective_map._put()` / `set_tech_layer()` Format-Mismatch: **nur**
   anfassen, wenn der zweite Durchlauf gewollt ist — dann zwingend zusammen mit
   einem Kaskaden-Guard auch in `apply_to_text`. Der Wächter-Test schlägt sonst an.
