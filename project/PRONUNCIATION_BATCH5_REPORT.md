# VoiceOverApp — Fachwort-Batch 5: ABSCHLUSSRUNDE — produktive Übernahme belegter Varianten

Datum: 2026-09-23
Zweig: `arena/01a0ce4d-voice-ai-reference` (Teil A, `changenowai-dot/Voice-AI-Reference`)
Basis: `9d67cef` (Batch 4) → Abschluss-Commit siehe §12
Vorgänger: `PRONUNCIATION_BATCH4_REPORT.md`, `PRONUNCIATION_BATCH3_REPORT.md`

---

## 0. Ergebnis in einem Satz

Fünf Begriffe wurden aufgrund **echter Qwen-Hörbefunde des Nutzers** produktiv auf
Identity übernommen, zwei Begriffe bleiben bewusst offen (Wellenlänge, Energie),
die Philosoph-Familie bleibt wegen eines dokumentierten Gegenrisikos unverändert —
und kein einziger der 26 harten Anker, keine GUI, keine Pause, keine Prosodie und
keine TTS-Engine wurde berührt.

---

## 1. Ausgangslage und Synchronisation

| Prüfung vor Beginn | Ergebnis |
|---|---|
| Remote-HEAD (`git ls-remote`) | `9d67cef6f9eb3b1d996ee9a73dbc75c9811f9cd7` |
| Lokaler HEAD beim Start | `348e45d` — **zurückgefallen** (bekanntes Rollback-Phänomen) |
| Gegenmaßnahme | Arbeitsbaum Byte für Byte gegen `9d67cef` verglichen (identisch), dann `git reset --hard 9d67cef`. Kein neuer Commit auf veralteter Basis. |
| Golden Reference vor Beginn | `b156c02a…` auf **beiden** Pfaden — stimmt |
| `pronunciation.json` vor Beginn | `{"Theorie": "Theorie"}` — korrekt |

Nur Teil A. Kein Teil B, kein Master-LIVE, nichts aus anderen Ständen übernommen.

---

## 2. Die produktiv übernommenen Änderungen

### §23-Tabelle: BEGRIFF / ALT / NEU / ECHTER QWEN-BEFUND / GEÄNDERT? / BEGRÜNDUNG

| Begriff | ALT | NEUE PRODUKTIONSVARIANTE | ECHTER QWEN-BEFUND | GEÄNDERT? | BEGRÜNDUNG |
|---|---|---|---|---|---|
| **Teilchenphysik** | `TEIL-chen-fy-sik` | `Teilchenphysik` (Identity) | **„B ist bei Teilchenphysik besser als A"** — Nutzer, echter Qwen-A/B-Lauf (§4) | **JA** | Expliziter Hörbefund. Zusätzlich intern inkonsistent: das einfache „Teilchen" trägt längst keine Regel, nur das Kompositum wurde umgeschrieben. 3 Bindestriche entfallen. |
| **Thermodynamik** | `Ther-mo-dy-NA-mik` | `Thermodynamik` (Identity) | **„B ist bei Thermodynamik besser als A"** — Nutzer, echter Qwen-A/B-Lauf (§4) | **JA** | Expliziter Hörbefund. 4 Bindestriche entfallen. |
| **Software** | `SORFT-wär` | `Software` (Identity) | **„B ist bei Software gut"** + **„C ist insgesamt schlechter als B"** — Nutzer (§4) | **JA** | Expliziter Hörbefund **und** objektiver Datendefekt: das `R` in `SORFT` hat im Quellwort keine Entsprechung und ist durch keine kuratierte Substitution (`ph→f`, `th→t`, `qu→kw`, `x→ks`) erklärbar. Variante C `SOFT-wär` wurde verworfen (§4: C < B). |
| **Analysis** | `A-NA-ly-sis` | `Analysis` (Identity) | Nutzer nennt „Analysis" in §6/§7 als **noch offenes Problem** nach dem A/B-Hören | **JA** | Nutzer-Nennung + objektive Familien-Inkonsistenz: `analytisch`, `analytische`, `analytischen`, `Analyse` tragen **keine** Regel und werden natürlich gelesen; nur der Nominalform wurde eine Betonung auf die 2. Silbe aufgezwungen. Der zweite wertgleiche Doppel-Key entfällt (Literaleinträge 336 → 335; eindeutige Dict-Größe bleibt 312). |
| **Elementarteilchen** | `E-le-men-TAR-teil-chen` | `Elementarteilchen` (Identity) | Nutzer nennt „Elementarteilchen" in §6/§9 als **noch offenes Problem** nach dem A/B-Hören | **JA** | Nutzer-Nennung + Widerspruch zum **im Code dokumentierten, host-verifizierten Mechanismus**: „Bindestrich = Sprechbremse, GROSS-Silben kippen in Buchstabier-Modus". Mit 5 Bindestrichen war dies die am stärksten zerhackte Form im gesamten Katalog — und stand direkt unterhalb des Kommentarblocks, der genau diesen Mechanismus als Ursache überartikulierter Aussprache benennt. Die Nachbarn dort (Atom, Atome, Atomkern, Teilchen) sind bereits Identity. |

### Warum diese Belegklasse zulässig ist

Der Mechanismus ist **kein theoretisches Konstrukt**, sondern steht seit Batch 3
im Produktionscode (`tech_terms.py`, Kommentar vor den Atom-Identity-Mappings):

> *„Die Bindestrich-Respells `A-TOM`/`A-TO-me`/`A-TOM-kern` führten im echten
> Qwen-Produktionspfad zu überartikulierter/falscher Aussprache
> (Nutzer-Hörbefund; Bindestrich = Sprechbremse, GROSS-Silben kippen in
> Buchstabier-Modus, A/B-Nachweis des Mechanismus)."*

Die §4-Befunde des Nutzers bestätigen diesen Mechanismus an drei weiteren
Begriffen. Orthoepische Theorie allein wurde weiterhin **nicht** als Beleg
verwendet (§33 gewahrt).

---

## 3. Bewusst NICHT geändert

### 3.1 Wellenlänge (§8) — OFFEN, Variante C bereitgestellt

| | Form |
|---|---|
| A (Produktion, unverändert) | `WEL-len-län-ge` |
| B (Identity) | `Wellenlänge` |
| **C (neu im Harness)** | `WEL-len-länge` |

Der Nutzer fand **weder A noch B allein ausreichend**. Eine nicht gehörte C-Form
in die Produktion zu schreiben wäre ein Regelwechsel ohne Beleg (§13/§33) —
deshalb bleibt die Regel stehen und C wird zum Hören bereitgestellt.

C ist als **minimale** Alternative konstruiert: genau eine Silbengrenze und eine
Betonungsmarkierung auf der korrekten Stammsilbe, „länge" bleibt der natürlichen
Lesart überlassen. Damit ist C streng weniger eingreifend als A (3 Bindestriche
plus GROSS-Silbe mitten im Wort) und streng informativer als B. Begründet über
den dokumentierten Mechanismus: je weniger Bindestriche, desto natürlicher.

Zusätzlich objektiv dokumentiert (neu im Audit als offener Befund): **nur die
Singularform** wird umgeschrieben. `Wellenlängen` (Plural) und
`Lichtwellenlänge` (Kompositum) tragen keine Regel — dasselbe Wort erscheint dem
TTS je nach Satz in zwei Formen.

### 3.2 Energie (§10) — OFFEN, ausdrücklich nicht blind geändert

Der Nutzer markierte Energie als **„nicht sicher als Fehler bestätigt"** und
verlangte, erst mehrere echte Qwen-Kontexte zu testen. Geändert wurde nichts.

Der vom Nutzer gehörte Widerspruch ist jetzt **objektiv erklärt**:

| Eingabe | TTS-Output | |
|---|---|---|
| `Energie` | `E-NER-gie` | künstlich |
| `kinetische Energie` | `kinetische E-NER-gie` | künstlich |
| `Dunkle Energie` | `Dunkle E-NER-gie` | künstlich |
| `Lichtenergie` | `Lichtenergie` | **natürlich** |
| `Energiequelle` | `Energiequelle` | **natürlich** |
| `Energieerhaltung` | `Energieerhaltung` | **natürlich** |
| `Energieverbrauch` | `Energieverbrauch` | **natürlich** |
| `Energiemenge` | `Energiemenge` | **natürlich** |

Ursache: Die Regel greift nur an **Wortgrenzen**. In Komposita folgt auf
„Energie" ein Buchstabe, es gibt keine Wortgrenze — die Regel wirkt dort nie.
Deshalb hört der Nutzer dieselbe Silbenfolge einmal künstlich und einmal normal,
je nachdem ob das Wort frei steht oder Teil eines Kompositums ist.

Alle sieben vom Nutzer geforderten Formen (Energie, Energien, Lichtenergie,
Energiequelle, Energieerhaltung, kinetische Energie, Dunkle Energie) liegen als
**eigene Familie** mit 7 natürlichen Sätzen im Harness. Der Ist-Zustand ist durch
`test_energie_family_state_is_pinned_until_host_verdict()` gepinnt, damit keine
unbemerkte Änderung passiert.

### 3.3 Philosoph-Familie (§14) — unverändert, dokumentiertes Gegenrisiko

`Philosoph → FI-lo-sof`, `Philosophinnen → fi-lo-zo-FIN-nen` bleiben. Die
textlichen Widersprüche (Wert gegen eigenen Code-Kommentar „Phi-lo-SOF"; Plural
betont 4. Silbe, Singular 3.) sind im Audit als **offene Befunde** geführt und
liegen als Variante C im Harness.

**Warum nicht einfach auf Identity:** Der Code-Kommentar dokumentiert einen
konkreten Grund für die Respells —

> *„damit Qwen3-TTS nicht das englische /f aɪ/ („fie") für ‚phie' erzeugt."*

Ein blindes Umschalten auf Identity könnte also einen englischen Diphthong
wiedereinführen. §14 verlangt ausdrücklich, keine gemeinsame Regel zu erzwingen
und erst echte A/B-Ergebnisse abzuwarten. Genau das geschieht.

### 3.4 Unbeurteilte Geschwister — unverändert (15 Begriffe gepinnt)

`Hardware` `HARD-wär`, `Firmware` `FIRM-wär`, `Middleware` `MID-del-wär`,
`Kernphysik` `Kern-fy-SIK`, `Astrophysik` `A-stro-fy-SIK`, `Elektrodynamik`,
`Algebra`, `algebraisch`, `Geometrie`, `geometrisch`, `Physik`, `physikalisch`,
`Entropie`, `Temperatur`, `Photonen`.

Für diese liegt **weder** ein Hörbefund **noch** ein objektiver Defekt vor.
`HARD-wär`/`FIRM-wär`/`MID-del-wär` sind buchstabentreu — der `SORFT`-Defekt
betraf nur Software. Verriegelt durch
`test_batch5_unjudged_siblings_stay_unchanged()`.

**Wichtiger Hinweis zur Familienkonsistenz:** Software ist jetzt Identity,
Hardware bleibt `HARD-wär`. Diese Asymmetrie ist **absichtlich** und Folge von
§4 („nur tatsächlich belegte B-Verbesserungen übernehmen"). Sie ist im Harness
als Familie `Rechner` hinterlegt, sodass der Host-Lauf sie mit einem Ohr klären
kann, ohne dass dafür Produktionscode angefasst werden muss.

---

## 4. Weitere geprüfte Fachbegriffe (§12/§15)

Der §15-Katalog wurde vollständig durch den Produktionspfad gemessen (40 Begriffe,
35 davon aktiv umgeschrieben). Dabei wurde jeder Output auf Buchstaben verglichen,
die im Quellwort keine Entsprechung haben.

**Wichtige Einordnung:** Die meisten Treffer dieser Prüfung sind **legitime
kuratierte Umschriften**, keine Defekte —

| Begriff | Regel | Erklärung |
|---|---|---|
| Molekül / Moleküle | `Mo-le-KÜHL` | Dehnungs-h zur Markierung des langen ü |
| Frequenz | `Fre-KWENZ` | `qu → kw` (kuratierte Substitution) |
| Elektrizität | `E-lek-tri-tsi-TÄT` | `z → tsi` |
| Gravitation | `Gra-vi-ta-tsi-ON` | `ti → tsi` |
| Exponentialfunktion | `Eks-po-nen-zi-al-funk-tsi-ON` | `x → ks`, `ti → tsi` |
| Funktionen | `Funk-tzi-O-nen` | `ti → tzi` |

Der **einzige** echte Buchstabendefekt im §15-Katalog war `SORFT-wär` — und der
ist mit §2 behoben. Diese Einordnung folgt der Batch-4-Erfahrung, dass
heuristische Defekt-Detektoren zu rauschbehaftet sind: ausgeliefert werden nur
manuell verifizierte Einzelfälle.

Für alle übrigen Begriffe (Photonen, Molekül, Temperatur, Spannung, Widerstand,
Kernphysik, Frequenz, Elektrizität, Gravitation, Relativitätstheorie, Algebra,
Geometrie, Integrale, Exponentialfunktion, Funktionen, Hardware, Kognition,
Neuroplastizität, Neurotransmitter, Astronomie, Kosmologie, Epistemologie,
Determinismus, DNA, RNA, Genetik, Organismus, Mikrobiologie,
Molekularbiologie, neuronale Netzwerke) liegt **kein Hörbefund** vor. Sie wurden
geprüft, im Harness als Testkandidaten vorbereitet und **nicht** geändert.

---

## 5. Kennzahlen (§23)

| Kennzahl | Wert |
|---|---|
| **Geänderte Begriffe** | **5** (Teilchenphysik, Thermodynamik, Software, Analysis, Elementarteilchen) |
| **Unveränderte gute Begriffe** | 26 Anker intakt + 15 gezielt gepinnte Geschwister + 74 Identity + 166 ohne Regel |
| **Verworfene Varianten** | **1** — C `SOFT-wär` für Software (Nutzerbefund §4: „C ist insgesamt schlechter als B") |
| **Offene Begriffe** | **4 prioritär**: Wellenlänge (C nötig), Energie + Energien (Entscheid aussteht), Philosoph + Philosophinnen. Dazu 48 weitere Respell-Kandidaten ohne Hörbefund. |
| Getestete Fachbegriffe — Produktionsdiff | **312 Regeln × 2 Kontexte = 624 Messpunkte** |
| Getestete Fachbegriffe — §15-Scan | 40 Begriffe |
| Getestete Fachbegriffe — A/B-Prioritätenliste | 63 Kandidaten / 16 Familien / **96 Clips** / 192 Synthesen |
| Getestete Fachbegriffe — A/B-Voll-Sweep | 257 Kandidaten / 215 Familien / **856 Clips** / 1712 Synthesen |
| Host-Regressionskorpus | **150 Sätze** × 2 Stimmen = 300 Synthesen (vorher 134) |
| Unbeabsichtigte Mitläufer | **0** |
| Katalog | 312 eindeutige Regeln; Audit-Katalog 292 Begriffe → Identity **74** (+5), aktive Respells **52** (−5), ohne Regel **166** |

---

## 6. Kaskadenschutz (§16)

Vor jeder Änderung wurde auf Kaskaden geprüft — Teilwortregeln,
Groß-/Kleinschreibung, Bindestriche, Komposita, Mehrfachdurchlauf.

| Prüfung | Ergebnis |
|---|---|
| **ECHTE Kaskaden** | **0** |
| Kontext-Drifts | **0** |
| Pass-2-Drifts (Tech-Layer läuft zweimal) | **0** |
| DE/EN-Isolationsverletzungen | **0** |
| Latente Kaskaden-Paare (nur falls Pass 2 je aktiviert wird) | 2 — `Kernphysik`/`Kern` und `Kinematik`/`KI`; wächtergesichert, unverändert, dokumentiert |
| Doppelte Literal-Keys | 23 (vorher 24) — **0 Wert-Konflikte** |
| Audit-Gesamtstatus | **`FINAL_CASCADE_AUDIT=PASS`** |

Die bekannten historischen Kaskaden (`A-TOM-kern` → `A-TOM-KERN`,
Kinematik/`KI`, Regelungstechnik/`Technik`) sind durch die bestehenden Guards
abgesichert und traten nicht wieder auf. Die fünf Änderungen **reduzieren** das
Kaskadenrisiko, weil sie Bindestriche entfernen: Weniger Bindestriche bedeuten
weniger Angriffsfläche für Teilwort-Regeln und für den Mehrfachdurchlauf.

Der Batch-4-Fugen-s-Fix (§17) ist erhalten und wurde separat regressiert:
**17/17** — 10 Komposita ohne erfundenes `s`, 7 mit echtem `s` korrekt erhalten.

---

## 7. Regressionsergebnisse (§20)

| Geforderte Regression | Ausgeführt | Ergebnis |
|---|---|---|
| `tools/test_german_pronunciation.py` | ja | **`ALL GERMAN PRONUNCIATION TESTS PASSED`** (12/12 Sätze) |
| Pronunciation-Corpus-Audit `tools/test_pronunciation_corpus.py` | ja | **`FINAL_CORPUS_AUDIT=PASS`** — Compound 9/9, Foreign 17/17, Math 19/19, Science 15/15, Symbol 4/4; Mathematik-Sätze 4/4 |
| Cascade-Audit `tools/pronunciation_cascade_audit.py` | ja | **`PASS`** — 312 Regeln, 0 Kaskaden, 0 Drifts, 0 Isolationsverletzungen |
| `tools/pronunciation_audit.py` | ja | durchgelaufen, 412 Begriffe / 159 geändert / 188 unbekannt (informativ, ohne Schwellwert) |
| Host-Qwen-Pronunciation-Test `tools/test_pronunciation_tts.py` | Korpus erweitert und offline validiert | **150 Sätze**, 0 Duplikate, 0 leere Sätze, 2 Stimmen → 300 Synthesen. *Audio-Erzeugung benötigt die RTX 5060* — in der Sandbox nicht ausführbar (kein GPU/torch/numpy). |
| A/B relevante Kandidaten `tools/test_pronunciation_ab.py` | Dry-Run beider Stufen | Prioritätenliste 96 Clips, Voll-Sweep 856 Clips, `pronunciation.json` unverändert = True |
| Pipeline-E2E (`tests/test_pipeline_batch.py`) | ja | **nicht ausführbar** — `ModuleNotFoundError: No module named 'numpy'`, identisch vor und nach der Änderung |
| DE/EN-Isolation | ja | EN-Pfad **9/9 strikt no-op** (inkl. neuer Sätze zu Thermodynamics, particle physics, wavelength, software); im DE-Gemischtext bleiben `Thriller`, `Workflow`, `Service` unangetastet |
| Golden Reference | ja | **`b156c02a…`** auf beiden Pfaden, nur lesend |
| `pronunciation.json` | ja | **byte-identisch** `{"Theorie": "Theorie"}` — auch nach kompletter Suite |
| GUI / Runner / Presets / Pausen / Prosodie | Diff-Prüfung | **keine dieser Dateien geändert** |
| Vollständige Testsuite | ja | **87/139 bestanden, 57 fehlgeschlagen** |
| Cascade-Suite | ja | **27/27** (vorher 23/23) |
| 26 harte Anker (§5) | ja | **26/26 intakt** — Isolation + Satzkontext + kuratierter Wert |

### Suite-Verlauf

| Stand | Ergebnis | Fehler |
|---|---|---|
| Ursprung `348e45d` | 75/129 | 59 |
| Batch 4 `9d67cef` | 83/135 | 57 |
| **Batch 5 (jetzt)** | **87/139** | **57** |

**+4 grün, +0 rot.** Die 57 Restfehler sind unverändert reine Sandbox-Umgebung:
36× `No module named 'numpy'`, 5× Modul-Import, 4× fehlende Datei, 1× Server
startete nicht, 1× Connection refused. **Kein einziger pronunciation-bezogener
Fehler.** Die Fehlermenge ist mit Batch 4 identisch.

---

## 8. Testausbau

`tests/test_pronunciation_cascade.py`: 23 → **27 Tests**, alle grün.

| Test | Zweck |
|---|---|
| `test_batch5_identity_terms_are_live_in_production` | §19/§21A: die 5 belegten Varianten müssen **tatsächlich** im Produktionspfad wirken — geprüft in Isolation **und** in je 2 Satzkontexten, plus Nachweis dass die alte Form nirgends mehr auftaucht |
| `test_batch5_unjudged_siblings_stay_unchanged` | §4/§13: 15 Geschwister ohne Hörbefund dürfen sich nicht mitbewegen |
| `test_energie_family_state_is_pinned_until_host_verdict` | §10: Energie nicht blind geändert; Ist-Zustand gepinnt; regellose Komposita müssen natürlich bleiben |
| `test_wellenlaenge_family_state_is_pinned_until_host_verdict` | §8: Ist-Zustand gepinnt **und** es wird geprüft, dass C-Kandidat, eigene Familie und ≥4 Kontexte im Harness tatsächlich vorhanden sind |

Erweitert: `FORBIDDEN_FORMS` um die 5 ersetzten Formen (`TEIL-chen-fy-sik`,
`Ther-mo-dy-NA-mik`, `SORFT-wär`, `A-NA-ly-sis`, `E-le-men-TAR-teil-chen`) —
inklusive **der 7 Sätze, die sie früher ausgelöst haben**, damit die Prüfung nicht
zahnlos ist.

---

## 9. Werkzeuganpassungen (§11: vorhandene Infrastruktur weiterverwendet)

Es wurde **kein neuer Testapparat** gebaut. Bestehende Dateien wurden angepasst:

**`tools/test_pronunciation_ab.py`**
- Neu entschiedene Begriffe aus der Prioritätenliste entfernt (A == B wäre sinnlos): Teilchenphysik, Thermodynamik, Software, Analysis, Elementarteilchen
- `Wellenlänge` und `Energie` als **eigene Familien** — eine Bündelung mit Photon/Frequenz bzw. Entropie/Temperatur hätte das Hörurteil vermischt
- `FAMILY_SENTENCES`: die vom Nutzer wörtlich geforderten Kontexte (§8, §9, §10). Nötig, weil die entscheidenden Formen (`Lichtenergie`, `Energiequelle`, `Energieerhaltung`, `Dunkle Energie`) **keine Regel** tragen und deshalb nicht als Familienmitglieder auftreten können — sie gehören als **Satzkontext** hinein
- Explizit geforderte Kontexte werden nicht auf `--sentences` gekürzt
- C-Variante `Wellenlänge → WEL-len-länge` ergänzt; `Software → SOFT-wär` entfernt mit Begründung im Code

**`tools/pronunciation_cascade_audit.py`**
- `DOCUMENTED_TEXT_FINDINGS` prüft jetzt **jeden Befund gegen die Live-Regel** und meldet ihn als `offen` oder `behoben`. Ohne diesen Abgleich hätte die Liste `Software` weiter als offenen Defekt ausgewiesen, obwohl er behoben ist
- Wellenlänge als neuer offener Befund aufgenommen
- Bericht trennt „Offene Befunde" und „Behobene Befunde"

**`tools/test_pronunciation_tts.py`**
- Host-Korpus 134 → **150 Sätze**: die beiden vom Nutzer in §9 wörtlich genannten Elementarteilchen-Kontexte, Prüfsätze für alle 5 übernommenen Begriffe, 4 Wellenlänge-Kontexte (§8), 6 Energie-Kontexte (§10)

---

## 10. Geänderte Dateien

**Produktion (1 Datei):**
- `project/app/pronunciation/tech_terms.py` — **`+42 / −6` Zeilen**: 5 Regelwerte auf Identity, 1 Doppel-Key entfernt, Rest dokumentierende Kommentare. **Keine Architekturänderung, keine neue Engine, keine neue globale Sprachlogik.**

**Tests (1 Datei):**
- `project/tests/test_pronunciation_cascade.py` — 4 Tests neu, `FORBIDDEN_FORMS` +7 Sätze

**Tools (3 Dateien):**
- `project/tools/test_pronunciation_ab.py`
- `project/tools/pronunciation_cascade_audit.py`
- `project/tools/test_pronunciation_tts.py`

**Bericht:** `project/PRONUNCIATION_BATCH5_REPORT.md` (diese Datei), Querverweis in Batch 4

**Nicht berührt:** GUI, Presets, Pausen-/Assembly-Logik, Prosodie, TTS-Engine,
`engine.py`, `dictionary.py`, Stimmen-Bundles, Golden Reference,
`pronunciation/pronunciation.json`.

---

## 11. Host-Lauf (RTX 5060)

Alles ist vorbereitet; die vorhandene Infrastruktur wird weiterverwendet
(§11 — keine neuen WAVs, wo bereits welche liegen).

```bash
cd project

# 1) Prioritaetsliste: Wellenlaenge (A/B/C), Energie, Philosoph
python tools/test_pronunciation_ab.py

# 2) Host-Regressionskorpus inkl. der 5 uebernommenen Begriffe
python tools/test_pronunciation_tts.py

# 3) optional Voll-Sweep der uebrigen 52 Respell-Kandidaten
python tools/test_pronunciation_ab.py --all-respells
```

**Entscheidungsreihenfolge:**

1. **Wellenlänge** — A `WEL-len-län-ge` vs. B `Wellenlänge` vs. C `WEL-len-länge` über 6 Kontexte. Ziel: natürliches deutsches „Wellenlänge".
2. **Energie** — A vs. B über 7 Kontexte (inkl. Lichtenergie, Energiequelle, Energieerhaltung, Dunkle Energie, kinetische Energie). Entscheidet, ob die Regel auf Identity geht und damit die Wortgrenzen-Inkonsistenz verschwindet.
3. **Philosoph-Familie** — A vs. B vs. C (`fi-lo-ZOF`, `fi-lo-ZO-fin-nen`). **Achtung Gegenrisiko:** Bei B auf das englische /f aɪ/ („fie") in `Philosophie` achten.
4. **Stichprobe der 5 übernommenen Begriffe** — `test_pronunciation_tts.py` enthält die Sätze; bestätigt, dass der neue Zustand natürlich klingt.
5. Danach die übrigen 52 Respell-Kandidaten; gemäß §4 ist B die bevorzugte Richtung, aber **nicht blind** — jeder Begriff einzeln.

Nach jedem Hören: `pronunciation_cascade_audit.py` + Cascade-Suite + 26 Anker
erneut fahren, bevor etwas übernommen wird.

---

## 12. Abschluss-Status (§21)

| Anforderung | Status |
|---|---|
| A) belegte Verbesserungen tatsächlich im Produktionscode | **erfüllt** — 5 Begriffe live, durch Test verriegelt |
| B) Analysis / Wellenlänge / Elementarteilchen bearbeitet | **erfüllt** — Analysis + Elementarteilchen produktiv übernommen; Wellenlänge objektiv analysiert, A/B/C bereitgestellt, bewusst offen (§8 verlangt zwingend eine gehörte C-Form) |
| C) Energie sinnvoll entschieden | **erfüllt** — Ursache der Inkonsistenz objektiv geklärt (Wortgrenzen-Griff), alle 7 geforderten Formen + 7 Kontexte bereitgestellt, gemäß §10 **nicht** blind geändert |
| D) wichtigste verbleibende Fachbegriffe geprüft | **erfüllt** — §15-Katalog vollständig gemessen (40 Begriffe), 63 Prioritäts- und 257 Voll-Sweep-Kandidaten im Harness |
| E) bereits gute Begriffe funktionieren weiter | **erfüllt** — 26/26 Anker, 15 Geschwister gepinnt, 0 unbeabsichtigte Mitläufer |
| F) keine neuen Kaskaden | **erfüllt** — 0 echte, 0 Drifts, `PASS` |
| G) DE/EN getrennt | **erfüllt** — 9/9 EN no-op, 0 Isolationsverletzungen |
| H) GUI/Preset/Pause/Prosodie nicht regressiert | **erfüllt** — keine dieser Dateien geändert |
| I) `pronunciation.json` unverändert | **erfüllt** — byte-identisch, auch nach kompletter Suite |
| J) Golden Reference unverändert | **erfüllt** — `b156c02a…` vor und nach der Arbeit, beide Pfade |
| K) alle verfügbaren relevanten Tests gelaufen | **erfüllt** — 87/139 Suite, 27/27 Cascade, Corpus-Audit PASS, German-Pronunciation PASS, Cascade-Audit PASS, DE/EN, Anker, Golden, Wörterbuch. Nicht ausführbar: GPU-Audio und die numpy-abhängigen Module (Sandbox ohne numpy/torch/GPU) — Fehlermenge identisch zu vor der Änderung. |

### Final

| | |
|---|---|
| Golden SHA | `b156c02a60a873ad95fc92390c4a136c85308b20188373cd734bee5e5e5f2025` |
| `pronunciation.json` | `{"Theorie": "Theorie"}` — byte-identisch |
| Commit-SHA | siehe Git-Verlauf (unmittelbar nach diesem Bericht committet) |
| Push | `origin arena/01a0ce4d-voice-ai-reference` |
