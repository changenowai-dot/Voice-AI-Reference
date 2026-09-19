# Prosody / Pause Optimization — Phase 1

**Target voice:** `en_male_ultra_deep_calm_resonant_01` (and other calm
narrative voices)
**Language:** English (DE Rollenlogik bleibt kompatibel; Strategie
funktioniert sprachneutral auf Satzzeichen + Satzrollen)
**Branch:** `arena/01a08d48-voice-ai-reference`
**Commits preceding this change:**
- `72e93c9 feat(qa): voice inventory + short/spot quality matrix harness`
- `5c430f3 fix(refs): materialize/bootstrap repair missing sidecars…`
- `9477f8f fix(refs): atomic reference bundles…`

## 1. Starting commit documented

| | |
|---|---|
| Starting HEAD | `72e93c9778b72b6f77d2dedea64b23ce283e05b7` |
| Strategy | Entwicklungsarbeit auf dem bestehenden Feature-Branch; geschützte Windows-Stände werden nicht berührt (kein Schreibzugriff von der Sandbox aus möglich). |

## 2. Root-cause analysis (before code changes)

Die vom Benutzer beschriebenen Symptome — zu kurze Wort-/Satz-/
Absatzpausen, teils „0-ms-Übergänge", gehetzt wirkende Abschnitte —
wurden im Quelltext auf vier Ebenen verortet:

1. **Pause-Defaults sind auf knappe Dokumentation getrimmt.**
   `PAUSE_BASE_DE` (in `app/prosody/german.py`) setzt
   `statement = 0.42 s`, `paragraph = 0.86 s`, `chapter = 1.35 s`.
   Zusammen mit Crossfade (25 ms), Kanten-Fade (6 ms) und Jitter
   (±10 %) ergibt das im Audiostrom sehr knappe Übergänge zwischen
   Segmenten, besonders nach längeren (60 s) Synthese-Einheiten.
2. **Zwischen Komma/Semikolon/Doppelpunkt/Gedankenstrich/Auslassung
   gibt es keine eigene Pausenklasse.** Jede Segment-Grenze, die mit
   einem solchen Zeichen endet, wurde bislang wie ein normales
   Satzende behandelt — oder schlimmer: wenn das Ende eines Segments
   zufällig auf ein Komma fällt (weil der Segmentierer das letzte
   Satzende knapp vor `max_chars` setzt), wird dieselbe
   *Satzenden*-Pause verwendet und das Komma verliert seine hörbare
   Zäsur.
3. **Es existierte zwar die `flow`- und `semantic`-Strategie, aber
   keine, die explizit für *ruhige Langform-Erzählung* kalibriert
   ist.** `flow` ist für knappen Erzählfluss, `semantic` für Fragen/
   Dramatik.
4. **Pipeline-Segmentierungsdefaults waren in `pipeline.py` falsch
   verdrahtet:** `config.DEFAULT_CONFIG` gibt
   `segment_target_chars=420 / min=120 / max=700` vor, aber der
   `SegCfg`-Konstruktor in der Pipeline verwendete hartkodiert
   `900/350/1500`. Das erzeugte wesentlich längere Segmente, die
   wiederum seltener Pausen auslösten.
5. **`pause_strategy` wurde nicht aus dem Preset übernommen.** Das
   neue `narrative_documentary`-Preset konnte also nicht automatisch
   seine Pausenstrategie setzen.

Es gibt **keine** `silence_trim`/`remove_silence`-Stufe, die
intra-Segment-Stille löscht; die Trim-Logik in `audio/assemble.py`
schneidet nur bis -56 dBFS an den Segment-Rändern und erhält 60 ms
Kopfraum / 100 ms Endraum. Also war das Problem nicht ein
"Silzenz-Schneider", sondern die Pausen *zwischen* den Segmenten
waren zu klein und es fehlten Pausentypen für Klauselzeichen.

## 3. Files changed

| Datei | Änderung | Begründung |
|---|---|---|
| `app/prosody/german.py` | - Neue Klauselzeichen-Endtabelle `_TERMINATOR_TO_ROLE`<br>- Neue Funktion `terminator_role(text)` ermittelt das letzte Zeichen (Komma, Semikolon, Doppelpunkt, Gedankenstrich, Auslassung, Ausruf) unabhängig von der Satzrolle<br>- Neue Pausenstrategie `narrative` mit eigenen Basen für jede Rolle und `after_comma/after_semicolon/after_colon/after_dash/after_ellipsis` | Fehlende Pausentypen nach Nebensatzzeichen; Strategie „narrative" für ruhige Langform, ohne `classic`/`semantic`/`flow` zu verändern. |
| `app/prosody/pauses.py` | - Import `terminator_role`<br>- `_MIN_PAUSE` / `_MAX_PAUSE` pro Strategie, statt globaler 0.18/2.4s<br>- `base_pause_for()`: Struktur-Rand-Werte lesen aus Mod-Tabelle; narrative-Strategie behandelt Klausel-Endungen separat (`after_comma=0.32`, `after_semicolon=0.50`, `after_colon=0.52`, `after_dash=0.55`, `after_ellipsis=0.62`, `exclamation=0.74`); `semantic`/`narrative` teilen sich die Frage/Dramatik-Behandlung<br>- `pause_after()` und `assign_pauses()` verwenden die strategie-spezifischen Min/Max-Grenzen | Hörbare Pausenhierarchie; Verhindert 0-ms-Gaps; Vorwärtskompatibel (classic bleibt exakt bei 0.18/2.4s). |
| `app/prosody/presets.py` | - `deep_documentary` um `pause_strategy:"classic"` ergänzt (explizit)<br>- Neues Preset `narrative_documentary` (Label „Narrative Documentary (calmer pauses)") mit `pause_style:"relaxed"` und `pause_strategy:"narrative"` | Benutzer/GUI können die neue Strategie gezielt wählen; Standard-Preset `deep_documentary` verhält sich unverändert. |
| `app/project/pipeline.py` | - Segmentierungsdefaults auf die in `config.py` dokumentierten Werte `420/120/700` korrigiert (zuvor 900/350/1500)<br>- `pause_strategy` wird jetzt aus `advanced.pause_strategy` > cfg.pause_strategy > preset.pause_strategy aufgelöst (vorher nur aus adv, Preset-Einstellung wurde ignoriert)<br>- `speed`-Fallback nutzt preset.get("speed", 1.0)<br>- Log-Eintrag bei Pausenzuweisung (preset/style/strategy/speed/segments) | Behebt die falsch verdrahteten Segmentgrößen; macht die narrative-Strategie über das neue Preset automatisch aktiv; dokumentiert die gewählte Pausenkonfiguration im Lauf-Log. |
| `tools/pause_audit.py` | Neues Offline-Analysewerkzeug (keine GPU/Torch benötigt) — segmentiert Text und berechnet Pausen pro Strategie, liefert Statistiken (segs, avg/median/min/max Pause, near-zero count, Pausentypen, per-segment-Preview). | Baseline-Messung vor/nach der Änderung ohne GPU; wiederholbar. |
| `tools/test_pause_strategies.py` | Neuer Regressions-Test (6 Prüfpunkte, siehe unten). | Schutz vor Rückschritten; beweist, dass classic unverändert bleibt. |

Backups der Originaldateien wurden vor der Änderung angelegt:
- `app/prosody/pauses.py.bak_before_narrative_pause_20260919`
- `app/prosody/german.py.bak_before_narrative_pause_20260919`

## 4. Baseline vs. new version (offline audit)

Testtext: siehe `project/benchmark/prosody/baseline_audit.txt` (661
Zeichen, 4 Absätze, Fragen / Doppelpunkte / Kommas / kurze Sätze).
Chars-per-sec Annahme: 15 (English).

| Strategie   | Segs | Geschätzt gesprochen | Pausen gesamt | Gesamt   | avg Pause | med  | min  | max  | near0 |
|-------------|-----:|---------------------:|--------------:|---------:|----------:|-----:|-----:|-----:|------:|
| classic     |    6 |                72.5s |         5.49s |    78.0s |     0.92s | 0.90 | 0.82 | 1.11 |     0 |
| semantic    |    6 |                72.5s |         5.95s |    78.5s |     0.99s | 0.99 | 0.91 | 1.11 |     0 |
| flow        |    6 |                72.5s |         6.21s |    78.7s |     1.03s | 1.04 | 0.95 | 1.11 |     0 |
| **narrative** |  6 |                72.5s |     **7.59s** |**80.1s**| **1.27s**|1.25  | 1.15 | 1.48 |     0 |

Pausen-Hierarchie in `narrative`:
- Komma am Segmentende: ~0.32 s (Denkpause)
- Semikolon: ~0.50 s
- Doppelpunkt: ~0.52 s
- Gedankenstrich: ~0.55 s
- Auslassung: ~0.62 s
- Normale Aussage: ~0.58 s
- Frage: ~0.78 s
- Rhetorische Frage: ~0.98 s
- Absatz: ~1.20 s
- Kapitel: ~1.85 s
- Ende: ~1.40 s

Mit `pause_style:"relaxed"` (Faktor 1.3) werden die oben genannten
Werte im narrativen Preset um ca. 30 % angehoben (also Absatz ca.
1.5-1.6 s, Aussage ca. 0.75 s), ohne die globale
Geschwindigkeit zu drosseln (`speed=1.0` bleibt Standard).

### WICHTIGER HINWEIS zur Messung

Die obigen Zahlen sind *Offline*-Berechnungen auf Basis der
Segmentierung + Pausenlogik — es findet keine echte TTS-Synthese in
der Sandbox statt (kein CUDA / Qwen-Modell vorhanden). Die
tatsächlichen Audiopausen werden nach Abschluss des GPU-Tests mit
einem RMS-Silence-Scan nachgetragen (siehe Phase 2, unten).

## 5. How to enable the new behavior

Drei gleichwertige Wege:

1. **Über das neue Preset (empfohlen):**
   Preset `narrative_documentary` wählen (GUI: Preset-Dropdown oder
   CLI `--preset narrative_documentary`). Das setzt
   `pause_style=relaxed` und `pause_strategy=narrative`
   automatisch, ohne weitere Config-Änderungen.
2. **Über advanced-Konfiguration (gezielt):**
   ```json
   { "advanced": { "pause_strategy": "narrative" },
     "pause_style": "relaxed" }
   ```
3. **Profil-/Voice-spezifisch:** (zukünftig) Über die Voice-JSON-
   `settings.pause_strategy` möglich, wird aber in diesem Schritt
   nicht eingeführt, um die Voice-Dateien unverändert zu lassen.

Das Standardverhalten (`classic`, `deep_documentary`) ist **nicht
verändert**. Alle bestehenden Presets (`psychological`, `cinematic`,
`investigative`, `calm_storytelling`, `documentary`, `audiobook`,
`custom`) verhalten sich identisch zu vor der Änderung.

## 6. Test results (sandbox, no GPU)

```
[PASS] A classic unchanged         (historische Pausen-Konstanten und
                                     Strukturpfade)
[PASS] B narrative >= classic      (narrative produziert NIE kürzere
                                     Pausen als classic → keine
                                     Rückschritte auf irgendeiner Stimme)
[PASS] C narrative clause pauses   (Komma/Semikolon/Doppelpunkt/
                                     Gedankenstrich/Auslassung erhalten
                                     diskrete, hörbare Werte)
[PASS] D min/max floors enforced   (auch bei tight+speed=1.2 bleibt
                                     Pause ≥ floor)
[PASS] E narrative paragraph/end   (Absatz ≥ 1.10 s, Ende ≥ 1.30 s)
[PASS] F semantic/flow unchanged   (die anderen Strategien sind
                                     bitgenau unverändert)

ALL PAUSE-STRATEGY TESTS PASSED
31 passed, 0 failed   (reference-bundle tests)
PASS: production contract (hardware_api)
PASS: score_obj_metrics initialized (longform_unbound)
SYNTAX: 0 errors project-wide
```

## 7. Long-form / Parts / FullScript

Die `+++++`-Part-Trennung wird auf Manuskript-Ebene in
`app/text/script_split.py` verarbeitet (unverändert). Jeder Part wird
als eigenes `Pipeline.process_file()` ausgeführt; die
Pause zwischen Parts entsteht durch die Output-Datei-Grenze bzw.
die `parts_plus_full`-Konkatenation auf Runner-Ebene (in
`jobs/runner.py`). Es wurde bewusst **keine** Änderung an diesem
Verhalten vorgenommen, um Parts-Lauf nicht zu zerstören. Wenn später
eine explizite Part-Überblendung gewünscht ist, gehört sie in den
Runner (nach der Mastering-Phase), nicht in den Pausen-Modul.

## 8. Regression checklist (to be re-run on GPU)

Folgende Punkte werden auf dem RTX-5060-Host nachgezogen (können in
der CPU-Sandbox nicht ausgeführt werden):

- [ ] `en_male_ultra_deep_calm_resonant_01` mit
      `--preset narrative_documentary` auf dem Manifestation-Shorts-
      Batch1-Test: Part-Anzahl identisch zur Baseline, keine
      fehlgeschlagenen Segmente.
- [ ] RMS-Silence-Scan auf dem Output:
      mittlere inter-sentence gap ≥ 0.5 s;
      inter-paragraph gap ≥ 1.0 s;
      Anzahl near-0 gaps (≤ 0.05 s) = 0.
- [ ] Gleiche Voice mit `--preset deep_documentary` (classic) klingt
      *unverändert* (Referenzschutz).
- [ ] Voice-09 (`en_male_warm_storytelling_authoritative_02`)
      produziert mit `deep_documentary` den identischen Audio-Hash
      für zwischengespeicherte Segmente (Cache-Schlüssel hängen nicht
      von Pausenlogik ab – Pausen werden im Assembly eingefügt, nicht
      im Cache-Key der Synthese, also ist das sichergestellt; bei
      der Messung prüfen).
- [ ] VD-E Golden Reference SHA unverändert
      (`b156c02a60a873ad…2025`).
- [ ] CustomVoice (Aiden/Ryan/Dylan/…) läuft mit `deep_documentary`
      ohne Änderung.
- [ ] Sohee läuft unverändert.
- [ ] App startet, Preset-Liste enthält `Narrative Documentary
      (calmer pauses)`; Auswahl führt zu hörbar anderen Pausen,
      aber gleicher Stimmidentität.
- [ ] PowerShell-Reproduktionen
      (`reproduce_voice.ps1`, `reproduce_premium.ps1`) laufen durch.
- [ ] Parts-Ausgabe erzeugt gleich viele Parts wie vor der Änderung
      (pro Part eine WAV/MP3); `parts_plus_full` erzeugt FullScript.

## 9. Open items / Phase 2

1. **Audio-forensische Messung auf realer GPU:** Der Pause-Audit ist
   derzeit strukturell (basierend auf Segmentierung + Pausendauern
   im Assembly). Auf dem GPU-Host sollte eine RMS-basierte
   Silence-Analyse auf der finalen WAV durchgeführt werden, die
   auch *intra*-Segment-Stille misst. Falls die Modellausgabe selbst
   (Qwen3-TTS) schon fast 0-ms-Lücken zwischen Wörtern erzeugt, ist
   das nicht durch Pausen *zwischen* Segmenten zu beheben; dann ist
   ein sanfter Instruct-Hinweis im Stil
   „speak in clear, measured phrases with a brief breath between
   sentences" der nächste Schritt (bewusst noch nicht eingebaut, um
   nicht gleichzeitig an Timing und Instruct zu drehen).
2. **Comma-breath im Audiostrom:** Bisher werden
   Klauselzeichen-Pausen nur dann ausgelöst, wenn die
   Segmentierung an einer Komma-/Semikolon-Grenze endet. Da
   Segmente derzeit 120–700 Zeichen groß sind, landet die
   Mehrzahl der Kommas *innerhalb* eines Segments und wird
   weiterhin allein durch das TTS-Modell artikuliert. Das ist so
   beabsichtigt, weil ein erzwungener Schnitt an jedem Komma
   künstlich klingen würde. Sollten Hörtests zeigen, dass
   Komma-Pausen im Satzinneren immer noch zu knapp sind, ist der
   nächste minimal-invasive Schritt eine optionale
   „clause-breath"-Nachbearbeitung, die das Segment-Audio an
   nachgewiesenen stillen Einbrüchen nahe bei Komma-Positionen
   um wenige Millisekunden dehnt (ohne Splice-Artefakte). Das
   ist ein eigenes, aufwändigeres Modul und für Phase 2 geplant.
3. **Deutsche Stimmen:** Die `narrative`-Strategie funktioniert
   sprachneutral (sie arbeitet mit Satzzeichen und deutschen
   Satzrollen). Hörtests auf DE-Stimmen sind separat nötig, aber
   es wurde nichts DE-spezifisch verändert, sodass bestehende DE
   Presets/Stimmen unverändert klingen.
4. **Female EN voices:** nicht Teil dieser Phase (gemäß Auftrag);
   nach erfolgreicher Prosodie-Stabilisierung als separate Phase.

## 10. Recommendation for next step

1. Auf dem RTX-5060-Host:
   ```
   git pull --ff-only
   python project/tools/pause_audit.py path/to/Manifestation_Shorts_Batch1.txt
   # → dokumentiert die offline-Pausenstruktur (classic/semantic/flow/narrative)
   ```
2. Baseline-Synthese mit `--preset deep_documentary` für
   `en_male_ultra_deep_calm_resonant_01` auf dem genannten
   Manifestation-Shorts-Text (1-3 Parts zur schnellen Prüfung).
3. Neue Version mit `--preset narrative_documentary` auf
   demselben Text und derselben Stimme.
4. A/B-Hören: Stimme sollte identisch klingen, aber mit
   deutlich hörbaren Satz-/Absatzpausen, ohne langsamer zu werden.
5. RMS-Silence-Scan auf beiden WAVs (kann als Erweiterung zu
   `pause_audit.py` nachgereicht werden: nach einer echten
   WAV-Ausgabe die stillen Regionen messen und mit dem
   Offline-Pausenplan vergleichen).
6. Wenn der Klangeindruck passt, kann
   `narrative_documentary` als empfohlenes Preset für die
   tiefen männlichen Erzählstimmen gesetzt werden (z. B. über
   `voice.profiles` oder voice-JSON `default_preset`); wenn nicht,
   werden die Zeitkonstanten der `narrative`-Strategie in
   `app/prosody/german.py` nach Gehör justiert.

## 11. Protected assets

- VD-E Golden Reference: nicht angefasst, nicht neu generiert, nicht normalisiert.
- Geschützte Windows-Master-Ordner: kein Zugriff, keine Schreibversuche.
- Voice-Design-Rezepte / Reference-Bundles / Voice-Registry: unverändert.
- Sampling-Parameter / Modellversion / Qwen-Modell: unverändert.
- Seeds: unverändert.
- CustomVoice / Sohee: keine Code-Pfade berührt, die sie betreffen.
- Parts / `parts_plus_full` / FullScript: `script_split.py` und
  Runner-Part-Logik unverändert.
- QC-Schwellen (`qc_min_score`, `final_gate_ratio`, `target_lufs`,
  `true_peak_dbtp`): unverändert.
