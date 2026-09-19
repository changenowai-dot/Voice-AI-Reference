# PHASE 1 COMPLETE — Deutsche Qwen3-TTS-Optimierung

**VoiceOverApp 1.1.0** · Auftrag: gezielte Optimierung der bestehenden
Pipeline für hochwertige **deutsche** Sprache (Qwen3-TTS 1.7B CustomVoice,
RTX 5060 / CUDA 12.8 / Python 3.12). Nicht neu gebaut — verbessert.

---

## 1. Baseline & Final Score (ehrlich eingeordnet)

| Messung | Wert | Kontext |
|---|---|---|
| Baseline DE-Score | **80.2** | GermanNaturalnessScore, 12 deutsche Testtexte, **Prüfstand-Engine** (Sandbox ohne GPU) |
| Final DE-Score | **80.6** | bester A/B-Versuch auf dem Prüfstand (+0.4) |
| Baseline auf **RTX 5060** | ⏳ ausstehend | `START.bat` → *Erweitert → 🇩🇪 Deutsche Baseline* bzw. `python app/main.py --german-baseline` |
| A/B auf **RTX 5060** | ⏳ ausstehend | `python app/main.py --german-ab` (übernimmt den Gewinner automatisch) |

**Wichtige Einordnung (§38/§62):** Diese Umgebung hat keine GPU und 2 GB
RAM — echte Qwen3-TTS-Synthese war hier unmöglich. Die Sandbox-Werte
beweisen die **Mechanik** (Baseline-Schutz, A/B, Vergleich, Übernahme),
nicht die akustische Endqualität. Alle Werkzeuge sind eingebaut und
laufen beim ersten Start auf der Zielhardware automatisch/fürsorglich
gegen die **dort** erzeugte, geschützte Baseline. Der Bericht
`benchmark/comparisons/report_AB.md` enthält dann Vorher/Nachher-Audio
und Zahlen. Keine Behauptung „Deutsch ist jetzt perfekt“ — gemessen,
verglichen, dokumentiert.

## 2. Durchgeführte deutsche Optimierungen

### 2.1 Normalisierung (§7, §12) — 10 echte Bugs/Verbesserungen
| Vorher | Nachher |
|---|---|
| 2001 → „zweitausendein“ | **„zweitausendeins“** |
| 1500 Bücher → „fünfzehnhundert Bücher“ | **„eintausendfünfhundert Bücher“** (Jahreslesart nur mit Kontext-Cue oder 19xx/20xx) |
| 5 Mio. Nutzer → „fünf Million. Nutzer“ | **„fünf Millionen Nutzer“** (kontextsensibler Numerus, Punkt-Rest beseitigt) |
| 1 Mrd. → „eins Milliarde“ | **„eine Milliarde“** |
| § 12 → „zwölf“ (§ gelöscht) | **„Paragraph zwölf“** |
| Ludwig XIV. blieb „XIV.“ | **„Ludwig der Vierzehnte“** (röm. Ordinalnamen) |
| Gedankenstrich „ – “ blieb Strich | **Komma-Pause** (Parenthese) |
| „…“ blieb Punkte-Rest | Satzende „.“ / Komma (dramaturgische Pause via Prosodie) |
| inkl./exkl. wirkten nicht | wirken (Key-Bug), + Std./Min./i.d.R./u.U./z.T./v.H. |
| rd. fraß „Mrd.“ („Mrund“) | Abkürzungen mit Wortgrenzen-Schutz |

### 2.2 Aussprache (§8–11)
- **Wörterbuch-Engine**: Sprachtrennung der Built-ins (EN-Builtins
  griffen vorher auch im Deutschen), erweitertes Format: exakte
  Schreibweise (`match: "exact"`), Alternativen (`alt`), Priorität,
  Sprache. `pronunciation.json` (Benutzer) bleibt erhalten und dominiert.
- **Eigennamen-Modul** (`app/pronunciation/names.py`): Gazetteer mit
  ~170 kuratierten Personen/Orten/Marken/Mythologie/Wissenschaft +
  Heuristik; riskante, ungedeckte Namen werden **gekennzeichnet und
  gemeldet** statt geraten (flagged spots, Bericht, UI).
- **Fremdwort-Entscheidung** (`foreign_words.py`): kontextabhängig —
  Anglizismus im deutschen Satz → deutsch-assimilierte Realisierung
  (Meeting→Mieting, Deep Learning→Dip Lörning, Psychology→Saikolodzi …);
  echte englische Phrase (≥3 Wörter/zitiert) → bewusst dem Modell
  überlassen; absorbierte Wörter (Computer) → unangetastet.
- Built-ins_de: **180 Einträge** (vorher 115), inkl. §9-Liste
  (Nietzsche, Göbekli Tepe, Kierkegaard, Psyche, CERN, NVIDIA,
  Psychology, Mindset, Attachment, Behavior …).

### 2.3 Deutsche Prosodie (§13, §14, §16)
- **Satzrollen-Analyse** (`prosody/german.py`): Frage/rhetorische Frage,
  Aufzählung, Kontrast, Betonung, dramatisch, emotional, Überschrift,
  Nebensatz-Erkennung.
- **Pausentypen**: grammatikalisch 0,42 s · Aussage · rhetorisch 0,74 ·
  dramatisch 0,88 · Absatz 0,86 · Kapitel 1,35 s (+ Mikro-Jitter ±10 %,
  kein mechanischer Takt).
- **Instruct-Sprachidentität** (statt „German accent“): 8 systematisch
  testbare Varianten (`de_doc_native` Default, `de_lang_de`,
  `de_cinematic`, `de_psych`, …), geprüft: keine „German accent“-Formulierung.
- Rollenbezogene Melodie-Hinweise (z. B. „rhetorical question: let it
  rise gently, leave space“), Aufzählungs-Rhythmus, Kontrast-Pause.

### 2.4 Quality Control & Regeneration (§21–§24)
- **GermanNaturalnessScore** (separat vom Gesamtscore): Aussprache
  (silbenbasiert, 4,2 Silben/s), deutsche Melodie (Deklination,
  Frage-Endmelodie, Spannweite in Halbtönen), Rhythmus (CV stimmhafter
  Abschnitte — mechanisch vs. natürlich), Pausen, Konsistenz,
  Fremdwörter, Namen, Zahlen. Ausdrücklich Vergleichsmaßstab.
- **Harte Regeln**: kritische Issues (rate_out_of_range,
  question_melody_missing, duration_implausible, no_voiced_speech,
  clipping, monotone, …) erzwingen Regeneration — **85 Punkte sind
  nicht automatisch „gut genug“**.
- **Gezielte Regeneration**: Fehlerklasse → spezifische Änderung
  (Aussprache→stabiler+Artikulation · monoton→Temperatur↑+Melodiehinweis ·
  Frage-Melodie→expliziter Hinweis · Tempo→Pace-Hinweis · Rhythmus→
  Streuung↑ · OOM→Segment-Split). Best-of-N-Varianten unterscheiden
  sich nachweislich (Seed+Parameter+Instruct-Fix).
- Deutscher Mindest-Score konfigurierbar (`german.min_german_score`, 75).

### 2.5 Stimmen (§19, §20)
- **Eigener deutscher Stimmen-Benchmark** (nicht die englischen
  Ergebnisse): 9 Speaker × deutsche Tests (Doku/Namen/Zahlen/Langform),
  Kriterien: DE-Score 55 %, Tiefe 15 %, Konsistenz 15 %, Tempo 15 %.
- Ermittelt **DEFAULT BEST GERMAN NARRATOR** und belegt alle 6 Profile
  automatisch (Male 3 = tiefster F0 der männlichen Top-3 → cinematic).
- Ergebnis wird in `config/config.json` (`german.best_speaker`,
  `voices.speaker_map`) gespeichert; UI-konfigurierbar.

### 2.6 Segmentierung & Tempo (§17, §18)
- Segmentgrößen-Sonde fester Teil des A/B (220/420/700 gegen
  Long-Form-Text, Gewinner wird übernommen).
- Tempo: pitch-erhaltend (ffmpeg atempo) + Instruct-Hinweis; keine
  Dehnung, die die Stimme unnatürlich macht.

## 3. Getestete Speaker / Parameter (auf Zielhardware ausführen)
- Speaker: Vivian, Serena, Uncle_Fu, Dylan, Eric, Ryan, Aiden, Ono_Anna,
  Sohee — Bewertung über `benchmark/german_speakers.md` (+ Hörproben
  `benchmark/german_voices/`).
- Instruct: 8 Varianten; Sampling: stable/balanced/expressive;
  Segmentgrößen: 220/420/700. Gewinner-Konfiguration landet automatisch
  in `config/config.json` und `versions.json`.

## 4. Performance (§32/§33/§34)
- **Qualität > Geschwindigkeit**; VRAM-Wächter aktiv; RTX-50xx braucht
  PyTorch cu128 (install.ps1 macht das, unverändert).
- **flash-attn**: NICHT installiert (Windows-Build-Risiko für cu128/
  Blackwell > Nutzen). Engine unterstützt jetzt
  `advanced.attn_implementation` ("sdpa" Default; "flash_attention_2"
  optional experimentell nach manueller Installation).
- **SoX**: qwen-tts importiert `sox` nur im 25Hz-Tokenpfad; wir nutzen
  ausschließlich 12Hz → **zur Laufzeit nicht erforderlich** (PyPI-Paket
  wird als qwen-tts-Abhängigkeit mitinstalliert, stört nicht). Keine
  manuelle Installation nötig; keine Änderung vorgenommen (§34).

## 5. Tests (§30) — Reproduzierbar
- **86/86 bestanden** (60 Bestands-Tests + 26 neue: GERMAN-01…10 +
  Baseline-Schutz + A/B + Stimmen-Mechanik + gezielte Regeneration +
  harte QC-Regeln + Regression „Batch/Cache/Resume/WAV/MP3/QC“).
- Damit nachweislich unversehrt (§29): Batch, Cache, Resume, WAV, MP3,
  Lautheitsnormalisierung, Quality Control, Fortschrittsanzeige,
  Aussprache-Wörterbuch, GPU-Pfad, Long-Form.
- **Bonus-Fund**: ein echter v1.0-JavaScript-Syntaxfehler (zusätzliche
  Klammer in `clearCache`) hätte die Web-UI im Browser stillgelegt —
  gefunden via Parser-Check, behoben.

## 6. Bekannte Einschränkungen
1. Echte akustische Bewertungen (Baseline/A-B/Stimmen) müssen auf der
   RTX 5060 laufen — Werkzeuge + Befehle fertig (siehe §1), Sandbox
   kann das nicht leisten.
2. Fremdwort-/Namen-Respellings sind kuratierte Heuristiken — falsche
   Einzelwerte sind über `pronunciation/pronunciation.json` vom Benutzer
   überschreibbar (höchste Priorität).
3. GermanScore bleibt ein Signalmaßstab: Frage-Melodie-Erkennung nutzt
   eine Autokorrelations-F0-Näherung; bei sehr kurzem Audio (<1 s) ist
   die Aussagekraft begrenzt.
4. Deutsch formulierte Instructs (`de_lang_de`) könnten je nach
   Modellversion schwächer wirken als englische — genau deshalb A/B.

## 7. Empfehlung für Phase 2
1. **Auf Zielsystem messen**: `--german-baseline`, `--german-ab`,
   `--german-speakers` (Reihenfolge) — danach erst Phase 2 starten.
2. VoiceDesign-Modelle (Apache-2.0, gleiche Familie!) als **zusätzliche
   Kandidaten** für die 6 Profile testen — gezielt für „tiefer, warmer,
   deutscher Dokumentarsprecher“, mit objektiven DE-Metriken + Hörtest.
3. Längeres A/B mit 2–3 Finalisten-Speakern über einen ganzen 10-Minuten-
   Text (Konsistenz über Distanz, nicht nur über 3 Segmente).
4. Optional: Whipser-basierte ASR-QC (lokal) als Aussprache-Verifikation
   ergänzen — dann Wirksamkeit der Respellings messbar in WER.
