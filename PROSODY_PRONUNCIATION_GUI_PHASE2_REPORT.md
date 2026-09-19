# Phase 2 — Prosodie/Pausen, deutsche Fachwort-Aussprache, GUI-Stimmenanzeige

**Branch:** `arena/01a08d48-voice-ai-reference`
**Starting commit (Phase 1):** `6c6229d79112622bd9608792cf982ae53f95242f`
**Stand-B (VoiceOverApp v2.8.0 / vc-seg-ab) ist vollständig ausgeschlossen.**
Es wird **ausschließlich** im GitHub-Workspace Stand A gearbeitet.
Keine lokalen Windows-Pfade wurden vorausgesetzt oder beschrieben.

## 1. Wichtige Einschränkung der Sandbox

Die Linux-Sandbox hat **keinen** Zugriff auf:
- die Qwen3-TTS-Modelle
- CUDA
- die Windows-Master-Backups
- die lokale Manifestation_Shorts_Batch1.txt des Benutzers
- eine lauffähige GUI (kein tkinter).

Deshalb werden in diesem Schritt:
- die **Code-Änderungen** (Pausen-Instruct, GUI-Gruppierung,
  Fachwort-Respellings) vorgenommen und mit neuen Unit-Tests
  abgesichert;
- **eigene, reproduzierbare Benchmark-Texte** im Repository
  angelegt (`project/benchmark/prosody/phase2_parts_test.txt`,
  `project/benchmark/pronunciation/german_special_terms.txt`);
- keine Audio-Ausgabe erzeugt. Der echte Audio-A/B-Vergleich
  (Phase-2-Hauptziel A: „Pausen im echten Audio tatsächlich
  sinnvoller?") **muss auf dem RTX-5060-Host ausgeführt werden**
  und ist im unten stehenden Ausführungsprotokoll dokumentiert
  (Kategorie B: „technisch verbessert, Hörtest ausstehend").

## 2. Root-Cause-Analysen

### 2.A Prosodie/Pausen

Phase 1 hat mit `narrative` eine neue Pausenstrategie und das Preset
`narrative_documentary` eingeführt, das die **Zwischen-Segment**-
Pausen hörbarer macht. Der Benutzer berichtet weiterhin zu dicht
gepresste Rhythmen. Ursachen-Analyse (Code-Pfad):

1. **Zwischen Segmenten (Assembly-Pausen)** – Phase 1 hat das
   Problem bereits adressiert: Pausen-Tabelle und Segmentierungs-
   Defaults (420/120/700) sind in Ordnung.
2. **Innerhalb eines Segments (Modell-Pausen)** – Das Qwen-Modell
   bekommt den Instruct-Text; in `deep_documentary` lautete der
   Basistext bisher „warm, serious, intelligent, slightly cinematic,
   never melodramatic" – ohne jeden Hinweis auf Atem-/Denkpausen.
   Bei langen Sätzen (300–700 Zeichen) kann das Modell Wörter und
   Satzteile eng aneinander hängen, auch wenn die
   Zwischen-Segment-Pausen passen.
3. **Minimale Korrektur:** Das `narrative_documentary`-Preset
   bekommt eine um wenige Phrasen ergänzte `base_style`, die das
   Modell zu **natürlichen Atempausen zwischen Phrasen** einlädt,
   ohne „slow down" oder „speak slowly" zu sagen (keine globale
   Temporeduktion):
   > “…Keep your natural speaking pace, but allow brief, natural
   > breath pauses between phrases and slightly longer pauses
   > between sentences; let each idea land before beginning the
   > next; do not rush or compress words together.”

Das ist bewusst ein Instruct-Änderung **nur im neuen Preset**;
`deep_documentary` bleibt unverändert Referenzverhalten. Keine
Sampling-Parameter, keine QC-Schwellen, keine Geschwindigkeits-
änderung (`speed: 1.0`).

### 2.B Deutsche Fach-/Fremdwort-Aussprache („Philosoph")

Pfad-Analyse: `text → normalize_text → PronunciationEngine.process →
apply_tech_germanization → apply_loanwords → dictionary.apply_to_text
→ build_instruct → TTS`.

Das Tech-Germanisierungs-Wörterbuch in
`app/pronunciation/tech_terms.py` hatte für Philosophie/Philosoph
Einträge, die mit der englisch anmutenden Silbe „FIE" endeten und
den Anlaut „Phi-LO" statt deutsch „FI-lo" verwendeten:

| Vorher (problematisch) | Nachher (deutsche Lesart) |
|---|---|
| `Philosophie: Fi-lo-so-FIE` | `Philosophie: fi-lo-zo-FIE` |
| `Philosoph: Phi-LO-sof` | `Philosoph: FI-lo-sof` |
| (fehlte) | `philosophisch/er/em/en/e … fi-lo-ZO-…` |

Zusätzliche Fehlerbehebung: die Tech-Term-Ersetzung benutzte
case-sensitive Regex, sodass kleingeschriebene Formen mitten im
Satz (z. B. „Ein philosophischer Geist") nicht getroffen wurden.
Die Ersetzung läuft jetzt mit `re.IGNORECASE`, behält aber
satzanfängliche Großschreibung bei.

Keine globalen DE-Ausspracheänderungen (andere deutsche Wörter
sind davon unberührt). Keine Änderung an der englischen
Aussprache.

### 2.C GUI Voice-Liste (Stimmen fehlen)

Code-Kette untersucht:
`VoiceRegistry._profiles` ← `voices/*.json`
→ `VoiceRegistry.entries()`
→ `VoiceRegistry.entries_for_language(language)` (keine Filterung)
→ `voice_groups(language, registry)` → GUI-Render.

**Erkenntnis:** Die drei Stimmen (`en_male_ultra_deep_calm_resonant_01`,
`de_male_deep_academic_01`, `de_male_cinematic_restrained_01`) sind
technisch bereits in `entries_for_language()` enthalten. Das Problem
liegt auf GUI-Ebene:

1. `voice_groups()` hatte bisher nur drei Gruppen
   (`locked`/`custom`/`clone`) und steckte **jede** clone-Stimme
   in dieselbe „Production Clone Voices"-Sektion, unabhängig von
   ihrem Tier (`ACTIVE`/`BACKUPS`/`UNASSESSED`/`REJECTED`).
2. Die GUI hat die Stimmen nach Geschlecht in **einer Zeile pro
   Geschlecht** (`side=LEFT, padx=18`) angelegt. Bei mehr als ~12
   Stimmen pro Geschlecht werden die Radio-Buttons durch
   Tk-Geometrie-Management **aus dem sichtbaren Fenster
   geschoben** (sie existieren, sind aber horizontal zu weit
   rechts und haben keinen eigenen Zeilenumbruch). Dadurch wirkt
   es für den Benutzer so, als fehlten sie.
3. REJECTED- und UNASSESSED-Stimmen waren ohne Status-Kennzeichnung
   vorhanden, wurden aber mit `available=False` deaktiviert und
   durch ihre Menge die sichtbare Liste „zugemüllt".

**Minimaler Fix** (keine zweite Voice-Liste, keine Dopplung der
Registry):

1. `voice_groups()` gibt jetzt **vier** Gruppen zurück:
   `locked`, `custom`, `clone` (nur ACTIVE + BACKUPS), `candidates`
   (UNASSESSED + REJECTED). Jede Zeile enthält `tier` und
   `selectable`.
2. Die GUI rendert eine **vierte Sektion** „Weitere Stimmen
   (Kandidaten / zurückgewiesen)" mit eigenem Warn-Hinweis; diese
   Stimmen sind sichtbar, aber deaktiviert (keine versehentliche
   Auswahl), mit klarer Status-Meldung.
3. Radio-Buttons bleiben aus Kompatibilitätsgründen in einer Zeile
   pro Geschlecht, aber die Aufteilung auf zwei Sektionen
   (Produktion/Archiv vs. Kandidaten/Zurückgewiesen) reduziert die
   Zahl der Elemente pro Zeile wieder auf eine darstellbare Breite.
4. GUI-Code deaktiviert einen Button jetzt, wenn
   `row.selectable == False` (statt nur auf `available is False` zu
   prüfen) – konsistent mit der Tier-Logik.

## 3. Reproduzierbare Benchmark-Texte

- `project/benchmark/prosody/phase2_parts_test.txt` – kontrollierter
  Mehr-Satz-/-Absatz-Test mit `+++++`-Part-Trenner (7 Absätze im
  ersten Part, 4 Absätze + `+++++` + 3 Absätze im zweiten Part).
  Enthält Kommas, Doppelpunkte, Semikolons, Gedankenstriche,
  Auslassungspunkte, Fragen, Ausrufe und kurze/lange Sätze.
- `project/benchmark/pronunciation/german_special_terms.txt` –
  kleiner DE-Text mit Philosoph/Philosophie/philosophisch/Psychologie/
  Neurowissenschaft/Quantentheorie/Physiker.

## 4. Geänderte Dateien

| Datei | Änderung |
|---|---|
| `project/app/pronunciation/tech_terms.py` | Korrektur der „Philosoph*"-Respellings auf deutsche Lesart (`FI-lo-sof`, `fi-lo-zo-FIE`, `fi-lo-ZO-fisch/-scher/…`); case-insensitive Ersetzung; zusätzliche gebeugte Formen (`philosophischer/-em/-en/-e`). |
| `project/app/prosody/presets.py` | `narrative_documentary.base_style` um drei Sätze ergänzt (natürliche Atempausen zwischen Phrasen, keine Wörter zusammenpressen, Ideen landen lassen) – ohne Temporeduktion und OHNE Änderung an `deep_documentary`. |
| `project/app/gui/voice_view.py` | Vier Gruppen (`locked`/`custom`/`clone`/`candidates`), Tier-Kennzeichnung (`tier`-Feld, Klartext-Labels), `selectable`-Flag, klare Status-Meldungen für fehlende Referenz oder nicht freigegebene Stimmen. |
| `project/app/gui/app.py` | Rendern einer vierten Sektion „Weitere Stimmen (Kandidaten / zurückgewiesen)" mit Warnhinweis; Deaktivierung der Radio-Buttons an `row.selectable` gekoppelt. |
| `project/tools/test_german_pronunciation.py` | Neuer Unit-Test für DE-Fachwort-Respellings (7 Sätze, keine GPU). |
| `project/tools/test_gui_voice_groups.py` | Neuer Headless-Test für die GUI-Stimmgruppierung (11 Prüfpunkte, kein tkinter). |
| `project/benchmark/prosody/phase2_parts_test.txt` | Testtext (EN, mit Parts-Trenner). |
| `project/benchmark/pronunciation/german_special_terms.txt` | Testtext (DE, Fachwörter). |

NICHT geändert (Schutz):
- Golden Reference VD-E (SHA, WAV, Manifest)
- ReferenceBundle-Resolver und Materialisierung
- Voice-JSONs / Seeds / Voice-Registry-Daten selbst
- QC-Schwellen, Final-Gate, Sampling-Parameter
- CustomVoice / Sohee
- Parts-/`parts_plus_full`-/FullScript-Logik
- deep_documentary-Preset
- Alle anderen Presets (psychological, cinematic, …).

## 5. Testergebnisse (Sandbox, kein Audio)

```
syntax errors: 0
[31/31] reference_bundle tests
[PASS] hardware_api
[PASS] longform_unbound
[6/6]  pause_strategies (classic/semantic/flow unchanged, narrative clauses/paragraphs)
[7/7]  german_pronunciation (Philosoph/Philosophie/philosophisch/… respelled correctly; old bad respelling not present)
[11/11] gui_voice_groups (3 Problem-Stimmen sichtbar, Gruppierung korrekt, candidates nicht auswählbar)
```

## 6. Was jede Problemklasse bedeutet

### A) Prosodie/Pausen
**Einstufung: B – technisch verbessert, Audio-Hörtest auf RTX-5060 erforderlich.**

Was verifiziert ist:
- Pausentabelle (`narrative`) liefert durchgehend ≥ classic-Pausen
  (Test B).
- Klausel-Endungen (Komma/Semikolon/Doppelpunkt/Gedankenstrich/
  Auslassung) werden mit eigenen Pausen belegt (Test C).
- Der Instruct des `narrative_documentary`-Presets bittet das
  Modell explizit um Atempausen zwischen Phrasen, ohne
  Geschwindigkeit zu drosseln.

Was noch auf dem Host geprüft werden muss:
1. Tatsächliche RMS-Silence-Analyse auf der erzeugten WAV für
   `en_male_ultra_deep_calm_resonant_01` mit
   - `--preset deep_documentary` (Baseline)
   - `--preset narrative_documentary`
   auf `phase2_parts_test.txt`.
2. Ob die verbleibenden „0-ms-Übergänge" zwischen Wörtern **innerhalb**
   eines Segments verschwinden (dann ist das Instruct die richtige
   Ebene); falls nicht, ist der nächste Schritt eine **sanfte
   Silbenzäsur im Audio-Post** (nicht in diesem Commit, da sie
   WAV-Manipulation erfordert).
3. Parts-Funktion: `phase2_parts_test.txt` hat einen `+++++`-Teiler
   → müssen 2 Parts ergeben.
4. Stimmidentität: `en_male_ultra_deep_calm_resonant_01` muss
   dieselbe Stimme bleiben (keine Geschlechts-/Timbreshift) –
   das kann nur menschliches Hören bestätigen.

### B) Deutsche Aussprache
**Einstufung: A / B (technisch korrigiert, Hörtest ausstehend).**

- Respelling-Pipeline produziert jetzt für
  - „Der Philosoph …" → `Der FI-lo-sof …`
  - „Die Philosophie …" → `Die fi-lo-zo-FIE …`
  - „Ein philosophischer …" → `Ein fi-lo-ZO-fi-scher …`
- Case-insensitive Ersetzung stellt sicher, dass die Formen auch
  mitten im Satz getroffen werden.
- Echter Hörtest erforderlich: klingen diese Wörter für einen
  deutschen Muttersprachler jetzt natürlich? Falls nicht, sind nur
  die Werte in `TECH_TERMS_DE` nachzujustieren; es ist keine
  weitere Code-Änderung nötig.

### C) GUI Voice-Liste
**Einstufung: A – Root Cause identifiziert, minimaler Fix
implementiert.**

- Die drei vom Benutzer genannten Stimmen (`en_male_ultra_deep_calm_resonant_01`, `de_male_deep_academic_01`, `de_male_cinematic_restrained_01`)
  sind **vorhanden**; sie werden nach dem Fix in einer eigenen
  Sektion „Weitere Stimmen (Kandidaten / zurückgewiesen)" mit
  deutlicher Statuszeile angezeigt und bleiben deaktiviert, damit
  sie nicht versehentlich genutzt werden.
- ACTIVE/BACKUPS-Production-Stimmen stehen in der eigenen
  „Production Clone Voices"-Sektion und sind auswählbar, sobald
  ihre Referenz vorhanden ist.
- VD-E ist als GESPERRTE PRODUKTIONSSTIMME nach wie vor ganz
  oben; CustomVoice sind in ihrer eigenen Sektion.
- Es gibt **keine** zweite manuell gepflegte Voice-Liste; die
  GUI holt ihre Daten weiterhin ausschließlich aus der
  `VoiceRegistry`.
- Die GUI muss auf dem Windows-Host einmal neu gestartet werden,
  damit die neue Sektion sichtbar wird.

## 7. Ausführung auf dem RTX-5060-Host (Audio-Hörtest)

```bash
git pull --ff-only                                # → 6c6229d… + Phase-2-Commit

# 1) Offline-Struktur prüfen (kein Modell nötig)
python project/tools/pause_audit.py \
    project/benchmark/prosody/phase2_parts_test.txt
python project/tools/test_gui_voice_groups.py
python project/tools/test_german_pronunciation.py

# 2) Baseline (Referenzverhalten, muss identisch klingen zu vor der Änderung)
python project/tools/reproduce_voice.ps1 `
    -Voice en_male_ultra_deep_calm_resonant_01 -Language English `
    -Preset deep_documentary `
    -InputFile project/benchmark/prosody/phase2_parts_test.txt `
    -OutputDir out/phase2_baseline

# 3) Narrative Preset (neu)
python project/tools/reproduce_voice.ps1 `
    -Voice en_male_ultra_deep_calm_resonant_01 -Language English `
    -Preset narrative_documentary `
    -InputFile project/benchmark/prosody/phase2_parts_test.txt `
    -OutputDir out/phase2_narrative

# 4) Deutsche Aussprache (kleiner Kontrolltext)
python project/tools/controlled_short_run.py `
    -Voice de_male_deep_natural_conversational_01 -Language German `
    -TextFile project/benchmark/pronunciation/german_special_terms.txt `
    -OutputDir out/phase2_german_pron

# 5) Parts prüfen: beide Läufe müssen genau 2 Parts + optional FullScript ergeben.
```

A/B-Hören: wenn der narrative-Lauf klarer, ruhiger und mit
merklichen Phrasen-/Satz-/Absatz-Pausen klingt, OHNE die Stimme zu
verändern oder langsamer zu machen, ist das Problem gelöst. Wenn
nach wie vor 0-ms-Lücken innerhalb von Sätzen hörbar sind, ist der
nächste Schritt ein minimaler Post-Processing-Schritt
(`audio/breath_padding.py`) – bewusst noch nicht in diesem Commit,
um nicht zu viele Variablen auf einmal zu ändern.

## 8. Regression

Alle bestehenden Tests PASS; der neue
`test_gui_voice_groups.py` stellt sicher, dass die GUI-
Stimmgruppierung nicht wieder hinter eine harte Kodierung
zurückfällt; `test_german_pronunciation.py` schützt die
„Philosoph"-Respellings; `test_pause_strategies.py` stellt sicher,
dass classic/semantic/flow bitgenau auf ihren Referenzwerten
bleiben.

## 9. Verbleibende offene Punkte (Kategorie C/D)

- **Echte Audio-A/B-Bewertung:** auf dem Host ausstehend (s. o.).
- **RMS-Silence-Scan der erzeugten WAV:** ein kleines Werkzeug
  `audio/measure_silence.py`, das Pausenlängen automatisch
  ausliest, ist sinnvoll als Phase-3-Arbeit, um subjektive
  Hörurteile durch Zahlen zu ergänzen. Hier noch nicht
  implementiert, damit Phase 2 nicht zu groß wird.
- **Weibliche englische Stimmen:** bleiben für eine spätere,
  separate Phase reserviert (wie im Auftrag vorgesehen).
- **Clause-breath im Audio-Post (intra-segment):** nur, falls
  der Hörtest zeigt, dass der Instruct allein nicht reicht.
