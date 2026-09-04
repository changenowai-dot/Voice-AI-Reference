# VoiceOverApp 1.0 — Lokales Long-Form-Voice-Over mit Qwen3-TTS

Automatische Erstellung hochwertiger Voice-Overs für YouTube (Psychologie,
Philosophie, Dokumentationen, Mystery, Deep Dives, Hörbuch-Erzählungen)
— **vollständig lokal, kostenlos, ohne API-Keys, ohne Abo**.

**TTS-Engine: ausschließlich Qwen3-TTS** (0.6B/1.7B, Apache-2.0).

---

## 1. Installation

1. Ordner entpacken (z. B. nach `C:\VoiceOverApp`)
2. **`install.ps1`** einmalig starten (Doppelklick oder Rechtsklick → *Mit PowerShell ausführen*) — oder einfach **`START.bat`** doppelklicken: Die Installation wird dann automatisch nachgezogen.

`install.ps1` installiert/prüft automatisch (alles kostenlos):

| Komponente | Quelle | Zweck |
|---|---|---|
| Python 3.10–3.13 | winget / python.org | Laufzeit |
| PyTorch **cu128** | download.pytorch.org | CUDA 12.8 — **erforderlich für RTX 5060/50xx (Blackwell)** |
| `qwen-tts` + transformers 4.57.3 | PyPI | Qwen3-TTS-Inferenz |
| FFmpeg | winget / gyan.dev | MP3 + Lautheits-Mastering |
| Qwen3-TTS-12Hz-1.7B-CustomVoice + Tokenizer | Hugging Face | Stimmodell (ca. 4 GB) |

Bereits vorhandene Komponenten werden wiederverwendet. Der Modell-Download
ist resumed-fähig (Abbruch + erneuter Start setzt fort).
`versions.json` dokumentiert die installierten Versionen (Reproduzierbarkeit).

## 2. Start

**NORMALER START (Desktop-GUI):**

- Doppelklick **`VoiceOverApp.bat`** (oder `START.bat`)
- bzw. Doppelklick auf **`VoiceOverApp.exe`** (nach einmaligem Build,
  siehe Abschnitt Build/`build_windows.ps1`)
- → es öffnet sich direkt die **echte Desktop-App (Tkinter-Fenster)**:
  PDF hineinziehen → Sprache/Stimme wählen → *Voice-over erstellen*.
  **Kein Browser, kein Webserver, kein Port 8750.**

**ENTWICKLERSTART (PowerShell):**

```powershell
.\VoiceOverApp.bat        # Desktop-GUI (Standard)
.\START.ps1               # Desktop-GUI (identisch, mit Install-Fallback)
```

**HEADLESS / CLI (Pipeline ohne GUI):**

```powershell
.venv\Scripts\python.exe app\main.py --headless --files "input\text.txt"
.\START.ps1 -Headless -Files "input\text.txt"
# weitere CLI: --info, --job <spec.json>, --desktop-voices, Benchmarks
```

Der alte Webserver ist **kein Standard mehr** und startet nur noch
explizit für Entwicklungszwecke: `.venv\Scripts\python.exe app\main.py --webserver`

Beim **ersten Start** automatisch: Hardware-Erkennung (GPU/CUDA/VRAM/RAM)
und Identity-Lock-Prüfung der VD-E-Referenz (Badge im Fenster).

## 3. Input (Eingabe)

- `.txt`-Dateien in den Ordner **`input/`** legen (eine oder viele)
- oder per **Drag & Drop** in die Weboberfläche ziehen
- Länge: ca. 10 Sekunden bis 120 Minuten Text pro Datei
- Ordner mit beliebig vielen Dateien werden automatisch im Batch verarbeitet
- (Architektur ist auf DOCX/PDF-Erweiterung vorbereitet; Version 1: `.txt`)

## 4. Output (Ausgabe)

Pro Eingabedatei erscheint in **`output/`**:

| Datei | Inhalt |
|---|---|
| `name.wav` | Master, 48 kHz / 24 Bit, **-14 LUFS / -1.5 dBTP** (Qualitätsmaster) |
| `name.mp3` | 320 kbps (praktische Endversion, YouTube-tauglich) |
| `report_*.md/json` | Batch-Bericht (Erfolge, Fehler, Scores, Wiederverwendung) |

## 5. Stimmen

Sechs Hauptstimmen-Profile (Anforderung der Spezifikation):

| Profil | Charakter | Qwen-Timbre |
|---|---|---|
| **Male 1 — DEFAULT BEST NARRATOR** | professionell, dokumentarisch, ruhig, glaubwürdig, warm | Ryan |
| Male 2 | tief, intelligent, hörbuchartig | Uncle_Fu |
| Male 3 | sehr seriös, kraftvoll, cinematic (Deep Dives) | Ryan (Tiefen-Instruct) |
| Female 1 | warm, ruhig, natürlich, vertrauenswürdig | Serena |
| Female 2 | intelligent, elegant, dokumentarisch | Sohee |
| Female 3 | professionell, emotional, erzählerisch | Vivian |

**DEFAULT BEST NARRATOR** ist voreingestellt. Die Zuordnung ist **nicht
willkürlich**: Der eingebaute *Stimmen-Benchmark* (Erweitert →
Stimmen-Benchmark) erzeugt standardisierte deutsche/englische Tests für
alle 9 Qwen-Timbres, bewertet sie (Tonlagen-/Lautheitsstabilität,
Intonationsbreite, Integrität) und legt hörbare Proben unter
`benchmark/voices/` ab. Empfehlung → `benchmark/voice_benchmark.md`.
Qwen3-TTS-Referenz: Deutsch-WER 1.7B = 0.634 (besser als GPT-4o-Audio,
lt. offizieller Modellkarte).

## 6. Presets

`Deep Documentary` *(Standard)* · Psychological · Cinematic · Investigative ·
Calm Storytelling · Documentary · Audiobook/Narrator · Custom.
Presets steuern Grundhaltung (Instruct), Pausenrhythmus, Emotionsempfehlung.

## 7. Geschwindigkeit

Regler **0.80× – 1.20×** (Standard 1.00×). Umsetzung pitch-erhaltend
(ffmpeg `atempo` auf dem Gesamtaudio) + Tempo-Hinweis im Sprach-Instruct.

## 8. Emotion & Intensität

`Emotion: AUTO` und `Intensity: AUTO` (Standard) — die App analysiert den
Text und wählt dezent passende Färbung (mysteriös, düster, gespannt,
hoffnungsvoll, warm, neutral) inklusive Intensität 1–5. Manuell
übersteuerbar (Erweitert). Die Grundhaltung bleibt für Long-Form-Konsistenz
stabil.

## 9. Aussprache

- Automatische Normalisierung: Zahlen, Jahreszahlen, Datumsangaben,
  Uhrzeiten, Prozent, Währungen, Einheiten, Abkürzungen, Akronyme,
  URLs, E-Mails, Sonderzeichen, römische Zahlen (DE + EN).
- **Aussprache-Wörterbuch** `pronunciation/pronunciation.json`:
  dauerhaft, editierbar (UI-Tabelle oder Datei), einzelne Einträge
  löschbar, komplett löschbar, unabhängig nutzbar. Mitgelieferte
  Basis-Einträge (Nietzsche, CERN, NVIDIA, Göbekli Tepe, ChatGPT, …)
  können jederzeit überschrieben werden. Priorität:
  **Benutzerwörterbuch > Built-ins > Modell**.
  Bei Unsicherheit wird nichts geraten, sondern der Begriff wird als
  Vorschlag gemeldet.

## 10. Cache

Jedes erfolgreiche Segment wird unter `cache/audio` + `cache/metadata`
gespeichert (Schlüssel = Text+Stimme+Sprache+Parameter+Engine). Gleiche
Segmente werden nie doppelt erzeugt — auch über Neustarts hinweg.

## 11. Resume

Projektzustände in `cache/projects`. Abbruch bei 93 %? → nächster Start
erzeugt **nur die fehlenden Segmente**. Abbrechen in der UI jederzeit
möglich (Schaltfläche *Abbrechen*), fertige Teile bleiben erhalten.

## 12. Fehlerbehebung

| Problem | Lösung |
|---|---|
| „CUDA nicht nutzbar" trotz RTX 50xx | PyTorch muss **cu128** sein (install.ps1 macht das). Neuinstallation: `.venv` löschen + install.ps1 |
| OOM / VRAM-Fehler | App reduziert automatisch (Cache leeren, Batch=1, Segment teilen). Dauerhaft: Erweitert → Modell `0.6B` |
| CPU-Modus sehr langsam | normal (0.6B ≈ Echtzeit×3–10 auf CPU). Für Produktion GPU verwenden |
| Kein MP3 | FFmpeg fehlt → install.ps1 erneut starten (WAV wird trotzdem erzeugt) |
| Aussprache falsch | Eintrag im Wörterbuch hinzufügen, Datei erneut starten (neue Segmente werden erzeugt) |
| Segmente klingen inkonsistent | Stimmen-Benchmark laufen lassen; ggf. Preset „Audiobook" + Tempo 1.0 |
| Logs | `logs/application.log`, `errors.log`, `quality.log`, `performance.log`, `install.log` |

## 13. Modellinformationen

- **Qwen3-TTS-12Hz-1.7B-CustomVoice** (+ **0.6B** als sparsame Variante),
  Tokenizer **Qwen3-TTS-Tokenizer-12Hz** — Alibaba Qwen Team, Jan 2026.
- 10 Sprachen inkl. **Deutsch** und Englisch; 24 kHz Ausgabe;
  Instruct-Steuerung (Emotion/Tempo/Stil); Sampling-Parameter
  (Temperature, top_k, top_p, repetition_penalty) frei konfigurierbar —
  die App optimiert sie per Benchmark statt Blind-Defaults.
- Lokal unter `models/`; nach Installation **offline** nutzbar.

## 14. Lizenzen

Siehe **`LICENSES.md`**. Kurzfassung: Qwen3-TTS-Modelle & -Code
**Apache-2.0** (kommerzielle Nutzung erlaubt), PyTorch BSD, transformers
Apache-2.0, FFmpeg GPL/LGPL (gyan.dev-Build: LGPL-kompatible Essentials;
Nutzung als separates Werkzeug), Python PSF. **Keine kostenpflichtigen
Komponenten.**

## 15. Technische Hinweise

- Architektur: modulare Pipeline (Analyse → Normalisierung → Aussprache →
  Segmentierung → TTS → QC → Regeneration → Zusammenfügen → Mastering).
  Module unter `app/` (text, pronunciation, segmentation, tts, voices,
  prosody, quality, audio, batch, cache, hardware, project, ui, …) —
  austauschbar für künftige Qwen-Versionen.
- Quality Score = Vergleichsmaßstab zwischen Varianten (Naturalness,
  Pronunciation-Plausibilität, Prosodie, Consistency, Audio-Integrity),
  **keine** absolute „Menschlichkeits-Messung“.
- Regeneration: bis zu 3 Versuche mit klassifizierter Parameter-Strategie,
  beste Version gewinnt; OOM-Notfallpfad teilt Segmente an Satzgrenzen.
- Pausen: kontextabhängig (Satz/Absatz/Kapitel/Frage/rhetorisch), mit
  reproduzierbarer Mikro-Variation — keine identischen Pausen.
- Datenschutz: Texte und Audio verlassen den Rechner nicht; Logs schreiben
  standardmäßig keine Textinhalte.
- Windows 10/11 getestet (Design), läuft grundsätzlich auch unter
  Linux/macOS (Pfade via pathlib).

---

## 16. Deutsche Qualitätsoptimierung (Phase 1 — Version 1.1.0)

Speziell für **hochwertige deutsche Sprache** (Details: `PHASE1_REPORT.md`):

- **Normalisierung**: Jahreszahlen mit Kontext („1500 Bücher“ ≠ „um 1500“),
  „zweitausendeins“, Mio./Mrd. mit korrektem Numerus, „§ 12“ → „Paragraph
  zwölf“, „Ludwig XIV.“ → „der Vierzehnte“, Gedankenstriche/Ellipsen als
  natürliche Pausen.
- **Aussprache**: erweitertes Wörterbuch (exakte Schreibweise,
  Alternativen, Sprache), ~170 kuratierte Eigennamen, kontextabhängige
  Fremdwort-Entscheidung (Anglizismen deutsch realisiert, echte
  englische Phrasen bleiben Englisch).
- **Deutsche Prosodie**: Satzrollen (rhetorische Frage, Aufzählung,
  Kontrast, dramatisch …) steuern Melodie-Hinweise und Pausentypen;
  8 systematisch getestete Instruct-Varianten mit expliziter deutscher
  Sprachidentität (kein „German accent“).
- **GermanNaturalnessScore**: separater Qualitätsmaßstab (Aussprache,
  deutsche Melodie, Rhythmus, Pausen, Konsistenz, Fremdwörter, Namen,
  Zahlen) + harte QC-Regeln (85 Punkte allein genügen nicht).
- **Gezielte Regeneration**: Fehlerklasse → spezifische Änderung
  (nicht zufällige Varianten).

**Auf der Zielhardware einmalig ausführen** (Erste Einrichtung →
*Erweitert → Deutsch-Optimierung*):

| Aktion | Effekt |
|---|---|
| 🇩🇪 Deutsche Baseline erzeugen | unveränderbarer Referenz-Vergleich (12 Texte, Audio + Scores) |
| 🇩🇪 Deutsch-Stimmen bestimmen | ermittelt DEFAULT BEST GERMAN NARRATOR aus deutschen Messungen, belegt die 6 Profile |
| 🇩🇪 A/B-Optimierung starten | testet Instruct/Sampling/Segmentgröße gegen die Baseline, übernimmt den Gewinner automatisch |

CLI: `python app/main.py --german-baseline` · `--german-speakers` · `--german-ab`

---

## 17. Phase 2 – Voice Studio & Blindvergleich (Version 1.2.0)

Wenn die Phase-1-Stimme nicht überzeugt (z. B. Ryan nicht gewünscht):

1. **Erweitert → Phase 2 – Voice Studio → „Phase-2-Vergleich starten“**
   (oder `python app/main.py --phase2-run`; Schnelltest: `--quick`)
2. Die App vergleicht mit dem **Kybalion-Text**: deine aktuelle
   Konfiguration, CustomVoice-Sweep (Speaker × Instruct-Varianten) und
   **6 VoiceDesign-Stimmen** (A/B/C aus dem Auftrag + 3 verfeinerte;
   erzeugt über Design→Clone für Langform-Konsistenz, Modelle werden bei
   Bedarf geladen).
3. **Blindproben anhören**: `benchmark/phase2/blind/sample_A.wav …` –
   neutral beschriftet; Zuordnung wird erst nach deiner Auswahl
   enthüllt (UI oder `--phase2-pick B`). **Dein Höreindruck entscheidet.**
4. Übernehmen: UI-Button oder `python app/main.py --phase2-apply` –
   VoiceDesign-Kandidanten laufen ab dann als Clone-Stimme in der
   Produktion; Phase 1 bleibt Fallback (Empfehlung + Konfiguration
   werden nur bei klarer Verbesserung bzw. deiner Auswahl geändert).

Weitere Phase-2-Mittel: neue Satzrollen (EXPLANATION/TRANSITION/CALM),
Hinweis-Budget gegen Überbetonung, rotierende Satzend-Anker,
Short-Run-Dramaturgie („Sieben Prinzipien. …“), Langsatz-Strukturierung,
Pausenstrategien (`classic/semantic/flow`, Test per `--phase2-pauses`,
aktivierbar über `advanced.pause_strategy`), Aussprache-Erweiterung
(Kybalion, Hermes Trismegistos, lateinische/wissenschaftliche Begriffe).
Ergebnisse liegen ausschließlich in `benchmark/phase2/` – Phase-1-Verzeichnisse
bleiben unangetastet. Details: `PHASE2_REPORT.md`.

---

## 18. Phase 3 – VD-E verfeinern, referenz-erhaltend (Version 1.3.0)

Deine gewählte VD-E-Stimme bleibt **gesperrt** (Hash-Manifest). Phase 3
optimiert ausschließlich um sie herum — mit Voice-Guard, der jede
Variation auf Tonhöhentreue zur Referenz prüft:

- **Fach-/Fremdwort-Aussprache (höchste Priorität)**: ~130 kuratierte
  deutsche Respellings mit Betonungs-Markierung (Theorie→teo-RIE,
  Quantentheorie→Quan-ten-teo-RIE, Kybalion→Kü-BA-li-on, Entropie,
  Philosophie, Phänomen …) + generische „…theorie“-Komposita-Regel.
  TTS-intern — dein Originaltext bleibt unverändert. Eigene Wörterbuch-
  Einträge gewinnen weiterhin immer.
- **Subtile Emotion**: 12 inhaltsausgelöste Zustände (Neugier, Zweifel,
  Staunen, Bedrohlichkeit …), budgetiert; niemals Global-Dramatik.
  Bug-Fix: englisches „war“-Muster verfälschte bisher deutsche Sätze.
- **Natürliche Variation**: semantische Sampling-Streuung (Clone-Stimmen
  per Default), Monotonie-Detektor für Langform.
- **Semantische Betonung**: 1–2 Schlüsselwörter je Satz, negierte
  Begriffe werden übersprungen.

Ablauf: *Erweitert → Phase 3* → Vergleich (BASE/TECH/VAR/TECHVAR ×
Fachwort-/Emotions-/Variations-/Melodie-/Kybalion-Batterien) →
Blindproben A–D anhören → wählen → übernehmen (**nur Schalter**, die
Stimme bleibt VD-E). Details: `PHASE3_REPORT.md`.

---

## 19. Desktop-App (Version 2.0.0) — GUI um die gesperrte Produktion

**Start:** Doppelklick `VoiceOverApp.bat` (Quellmodus) oder gebaute
`VoiceOverApp.exe` (`build_windows.ps1`). Workflow: **PDF hineinziehen**
→ Text prüfen/editieren → **Deutsch/English** → **Stimme** (VD-E =
Standard, Ryan, Aiden · Vivian, Serena, Sohee) → Tempo/Format/Ordner →
**VOICE-OVER ERSTELLEN** → echter Fortschritt (Segment i/n, QC,
Restzeit) → WAV/MP3/Ordner/Bericht öffnen.

- Der Produktionskern (VD-E, Pipeline, QC, Regeneration, Cache, Resume)
  ist **unverändert und gesperrt**: Identity-Lock prüft den VD-E-Hash
  bei Start, vor jedem Lauf und nach jedem Backend-Lauf — Abweichung ⇒
  VD-E deaktiviert, keine „Reparatur“.
- **Final-QC-Gate** (neu): kritische Ergebnisse und Split-Fallbacks
  werden vor Übernahme erneut geprüft — nie beschädigtes Audio als
  „fertig“.
- Backend = genau ein Subprocess (JSONL-Fortschritt, PID-Sperre gegen
  parallele GPU-Prozesse). Headless/CLI bleibt vollständig erhalten.
- **PDF-Import** (pypdf, lokal): Drag&Drop, mehrseitige PDFs,
  Artefakt-Bereinigung ohne Inhaltsveränderung; Editor mit
  Zeichen-/Wort-/Dauer-/Segment-Schätzung.
- Cache-Version `q3p-v2-integrity`; Produktionssamen 52001;
  Expressive Sampling; Headroom 5 s (`config/production.json`, LOCKED —
  siehe `FINAL_VOICE_SETTINGS.txt`).
- Stimmen-Report: `python app/main.py --desktop-voices`
  (DE+EN je Stimme, Klassifikation Empfohlen/Sehr gut/Gut/Experimentell).
- Streaming-Assembly: 120-Minuten-Texte ohne Speicherproblem.

Details: `FINAL_APP_REPORT.md`.

---

## 20. v2.1.0 — Native-Language-Stimmen & Long-Script-Splitting

**Stimmen (Sprache zuerst wählen — die Liste passt sich an):**

| Deutsch | Status | Englisch | Status |
|---|---|---|---|
| **VD-E** (tief, ruhig, seriós) | **EMPFOHLEN · Standard** (LOCKED) | Ryan (nativ Englisch, dynamisch) | NATIV · EMPFOHLEN |
| Uncle_Fu (tief, warm, mellow, reif) | CROSS-LANGUAGE | Aiden (nativ Englisch, sonnig) | NATIV · EMPFOHLEN |
| Dylan (klar, natürlich, jünger) | CROSS-LANGUAGE | Uncle_Fu (tief, mellow, reif) | FALLBACK |
| Serena (warm, sanft, ruhig) | CROSS-LANGUAGE | Serena | CROSS-LANGUAGE |
| Vivian (hell, klar, jung) | CROSS-LANGUAGE | Vivian | CROSS-LANGUAGE |
| Sohee (warm, emotional, reich) | CROSS-LANGUAGE | Sohee | CROSS-LANGUAGE |

Pro Sprache 3 männliche + 3 weibliche Stimmen. Native-Status und
Klangcharakter werden getrennt angezeigt; es gibt **kein natives
deutsches Preset** — VD-E ist die gesicherte deutsche Hauptstimme,
kein Preset wird je fälschlich „nativ deutsch/englisch-weiblich“
genannt. Neue Stimmen: einfach zusätzliche `voices/*.json`.

**Long-Script-Splitting (optional):** Marker `+++++` **allein auf einer
Zeile** erzeugt Abschnitte — nie zeitbasiert (kein Auto-Schnitt nach
30/60 s). Ausgabemodi: **Gesamtdatei** (Standard, exakt wie bisher) ·
**Nur Parts** (`Part_001.wav/mp3…`, Shorts-tauglich) · **Parts +
Gesamtdatei** (`FullScript.wav/mp3` wird aus den fertigen Parts
zusammengefügt — keine erneute TTS-Synthese, identisches Material).
Aussprache/QC/Cache/Resume wirken pro Part identisch wie bisher.

VD-E unverändert: SHA-256-Lock, Recommended, Default, Produktionseinstellungen (Tests 179/179).

---

*Erstellt autonom durch den Arena.ai Agent — technische Umsetzung,
Testabdeckung und Grenzen siehe `FINAL_APP_REPORT.md`, `TESTREPORT.md`
und die Phasenberichte im Auslieferungs-ZIP.*
