# TESTREPORT – VoiceOverApp 1.0

Erstellt: 28.08.2026 · Ersteller: autonomer Arena.ai-Agent
Build: `VoiceOverApp.zip`

## 1. Zusammenfassung

| Bereich | Status | Getestet wo/wie |
|---|---|---|
| Text-Normalisierung DE/EN (Zahlen, Daten, Zeiten, Währungen, Abkürzungen, Akronyme, URLs, E-Mails, röm. Zahlen) | ✅ 60 Unit-/Integrationstests | Linux-Sandbox (CPU), deterministisch |
| Textanalyse & Satzgrenzen | ✅ | Sandbox |
| Aussprache-Engine + Wörterbuch (CRUD, Persistenz, Priorität, Grenzen, Vorschläge) | ✅ | Sandbox |
| Segmentierung (keine Wortverluste, Clausel-Split, Absätze/Kapitel, Größenlimits) | ✅ | Sandbox |
| Pausen (kontextabhängig, variiert, Stile) | ✅ | Sandbox |
| Prosodie/Instruct (AUTO-Emotion, Intensität, Frage-Melodie, Presets) | ✅ | Sandbox |
| Pipeline (Analyse→…→Master→Bericht) | ✅ Tests A–Q (Logik) | Sandbox mit deterministischer TestDouble-Engine |
| Quality Control + Regeneration (Best-of-N, Fehlklassifikation→Strategie) | ✅ | Sandbox (echte Signalanalyse, echte Defekte injiziert) |
| Cache + Resume (über Neustarts, Teilverlust, Textänderung) | ✅ | Sandbox |
| Batch + Fehlerisolierung + Bericht | ✅ | Sandbox |
| Mastering: LUFS -14 / TP -1.5, WAV 24bit/48k, MP3 320k | ✅ | Sandbox mit **echtem ffmpeg 7.0.2** |
| Lautheitsmessung (EBU R128 K-Filterung, Gating) | ✅ gegen Referenzsignale | Sandbox |
| Hardware-Erkennung + Modi + VRAM-Wächter | ✅ CPU-Pfad; GPU-Pfad Code-review + Mock | Sandbox ohne GPU |
| Qwen3-TTS-Engine (Aufrufparameter, OOM-Pfad, Fehlerklassen, Seeds, Entladen) | ✅ mit gemocktem `qwen_tts`/`torch` | Sandbox |
| Weboberfläche (API, Upload/Drag&Drop, Start/Stop, Fortschritt, Wörterbuch, Cache-Sicherheit, Pfad-Traversal-Schutz) | ✅ echter HTTP-Ende-zu-Ende-Test | Sandbox |
| System-Benchmark & Stimmen-Benchmark (Ablauf, Berichte, Empfehlungen) | ✅ Quick-Modus | Sandbox |
| **Echte Qwen3-TTS-Synthese auf RTX 5060** | ⏳ **auf Zielhardware ausstehend** | erster START.bat-Lauf → System-Benchmark |
| Windows-Skripte (install.ps1/START.ps1/START.bat) | ⏳ Code-review + PowerShell-Konventionsprüfung; Ausführung auf Zielhardware | Zielsystem |

**Testergebnis Sandbox: 60/60 bestanden (0 Fehler)** – `tests/run_all.py`.

## 2. Was hier NICHT behauptet wird (Anforderung 62)

- Die **subjektive Sprachqualität** (Natürlichkeit der deutschen Stimmen)
  konnte in dieser Umgebung nicht angehört werden: Die Sandbox hat keine
  GPU und nur 2 GB RAM — echte Qwen3-TTS-Inferenz ist dort unmöglich.
- Deshalb: Beim ersten Start auf dem Zielsystem führt die App den
  **System-Benchmark** (GPU, Modell, Deutsch/Englisch-Test, VRAM, Tempo,
  WAV/MP3, Long-Form, Segmentgrößen-, Sampling-Probe) und den
  **Stimmen-Benchmark** (alle 9 Qwen-Timbres × DE/EN, hörbare Proben in
  `benchmark/voices/`) durch bzw. bietet sie per Klick an. Diese
  Messungen auf der RTX 5060 entscheiden final über Segmentgröße,
  Sampling-Parameter und die beste DEFAULT-BEST-NARRATOR-Belegung
  (Anforderung 19+20), statt dass hier ungetestete Behauptungen aufgestellt
  werden.
- Voreinstellungen, die auf offiziellen Qwen3-TTS-Benchmarks basieren
  (Deutsch-WER 0.634 für 1.7B-CustomVoice — lt. Modellkarte besser als
  GPT-4o-Audio), sind als fundierte Startpunkte dokumentiert und werden
  vom Benchmark auf der Zielhardware verifiziert/überschrieben.
- „TestDouble“ ist ausdrücklich **kein** Produktions-/Fallback-Engine
  (Anforderung 2), sondern ein deterministischer Prüfstand ausschließlich
  für automatisierte Tests (`--engine test_double`, nicht in der UI
  erreichbar).

## 3. Durchgeführte Tests im Detail (Abbildung A–Q)

| Test | Ergebnis |
|---|---|
| A: 10-Sekunden-Text | ✅ (Test `test_a_10_seconds_text`) |
| B: 1-Minuten-Text | ✅ |
| C: 10-Minuten-Text | ✅ (14 s Laufzeit, stabil, Score Ø > 50) |
| D: Long-Form mit Kapiteln/Struktur | ✅ (LUFS-Konsistenzziel erreicht) |
| E: Deutsch | ✅ (inkl. Normalisierungs-Zählung) |
| F: Englisch | ✅ |
| G: Aussprache (schwere Begriffe) | ✅ (Built-ins + Regeln) |
| H: Aussprache-Wörterbuch | ✅ (CRUD/Persistenz/Priorität/Löschung) |
| I: mehrere Dateien (Batch) | ✅ (5 Dateien) |
| J: Cache (2. Lauf 100 % Wiederverwendung) | ✅ |
| K: Resume (Teilverlust → nur Fehlendes) | ✅ |
| L: Quality Control (Defekt-Injektion) | ✅ |
| M: automatische Regeneration (Best-of-N) | ✅ |
| N: WAV (16/24 bit, Roundtrip) | ✅ |
| O: MP3 (320k, Header-Prüfung) | ✅ |
| P: Audio-Normalisierung (-14 LUFS ±1, TP-Limit) | ✅ |
| Q: GPU-Beschleunigung | CPU-Pfad ✅; GPU-Pfad: Erkennung/Modi/OOM-Schutz implementiert + mockgetestet, echte Ausführung = System-Benchmark auf Zielsystem |

Zusätzlich über A–Q hinaus: UI-Ende-zu-Ende (HTTP), Fehlerisolierung,
Benchmark-Läufe, Hardware-Erkennung, Konfigurationslogik, Engine-Mocks
(Parameter/OOM/leeres Audio/fehlendes Paket), Pfad-Traversal-Schutz,
Cache-Clear-Sicherheitsabfrage.

## 4. Bekannte Grenzen (dokumentiert, Anforderung 62)

1. **Erste echte Synthese auf Zielhardware**: Beim ersten Start lädt die
   App das Modell (einmalig). Sollte die CUDA-Pytorch-Installation
   scheitern, fällt install.ps1 automatisch auf CPU zurück (langsam,
   aber funktional; 0.6B wird dann bevorzugt).
2. **Stimmen-Zuordnung**: Die 6 Profile sind auf Basis der offiziellen
   Timbre-Beschreibungen + Deutsch-WER-Daten zugeordnet. Der
   Stimmen-Benchmark erzeugt Hörproben und eine Empfehlung; die finale
   Auswahl kann der Nutzer in der UI treffen (Anforderung 19 sieht Test
   vor — bereitgestellt als integrierter Benchmark statt behauptet).
3. **Quality-Score-Metriken** sind Signalkriterien zum Variantenvergleich,
   keine absolute Natürlichkeitsmessung (Anforderung 46 eingehalten).
4. **Ohne ffmpeg**: nur WAV-Master (numpy-Fallback), kein MP3 —
   install.ps1 installiert ffmpeg automatisch; Grenze wird in UI/Log gemeldet.
5. **Spracherkennung** (fehlende Wörter via ASR) ist bewusst nicht
   eingebaut (Schwere, Lizenz, Lokalität); QC nutzt Dauerplausibilität
   als Proxy — dokumentiert.
6. Windows-Skripte wurden konventionsgeprüft (PowerShell 5.1-kompatibel),
   aber nicht auf Windows ausgeführt (Sandbox ist Linux).

## 5. Reproduzierbarkeit (Anforderung 74)

- `tests/run_all.py` führt die gesamte Suite aus (kein pytest nötig).
- `versions.json` + `environment.json` (nach System-Benchmark).
- `requirements.txt` + `install.ps1` (PyTorch cu128 für RTX 50xx).
- Isolierte Testläufe via `VOICEOVER_ROOT` (kein Eingriff in echte Ordner).

## 4a. v2.1.0 — Native-Language-Stimmen & Splitting

- **179/179 Tests bestanden** (159 Bestand + 20 neue: Voice-Architektur
  je Sprache, keine Native-Falschaussagen, Marker-Exaktheit, Modi A/B/C
  E2E, FullScript = Part-Material (array-gleich), VD-E-Kernschutz).
- VD-E unveraendert (production.json, Identity-Lock, Recommended,
  Default); TTS-Kern nicht beruehrt (TTS_CORE_CHANGED=NO).

## 4b. Packaging-Fix (v2.0.0, final) — Start-Schichtung

- **159/159 Tests bestanden** (143 Bestand + 16 neue: START.bat/ps1
  starten GUI, Routing-Matrix (GUI/CLI/Webserver-explicit), desktop.py
  Entry, Spec (2 EXEs: GUI windowed + Backend console), build-Skript
  relativ + Hash-Check, Voice-Profile unverändert, production.json
  unverändert, Identity-Lock-Mechanik, README/Manifest/Report/Korrektur,
  CLI erhalten).
- Startbaum jetzt: START.bat/VoiceOverApp.bat/START.ps1/desktop.py/EXE →
  **Desktop-GUI**; Webserver nur mit explizitem `--webserver`.
- Keine TTS-/Audio-Kern-Änderung (TTS_CORE_CHANGED=NO).
- WINDOWS_GUI_RUNTIME_TEST_REQUIRED (Sandbox ohne Display/Windows-SDK).

## 5. Desktop-App (v2.0.0) — GUI um den gesperrten Produktionskern

- **143/143 Tests bestanden** (122 Bestand + 21 Desktop-Tests: PDF,
  Identity-Lock, Produktionsschalter, Registry/Fallback-Verbot,
  Final-Gate, Job-Runner-JSONL, Einzelprozess-Lock, §34-Matrix
  DE/EN×6 Stimmen, §35-Long-Form-Kette PDF→WAV/MP3 mit ~37 min Audio).
- Produktionskern unverändert; Ergänzungen: Final-QC-Gate (§4),
  Streaming-Assembly (§18, Speichersicherheit 120 min+),
  Identity-Lock-Integration, Job-Runner, GUI (tkinter+windnd),
  Voice-Registry, Desktop-Voice-Benchmark, Packaging-Skripte.
- Behobene echte Fehler: Lock-Fehler außerhalb try/except (stummes
  Sterben), tmpfs-Überlauf der Testumgebung, unrealistische
  Prüfstand-Sprechrate (5,9→4,2 Silben/s), In-Memory-Assembly-OOM.
- Nicht in der Sandbox prüfbar (ehrlich): grafisches Öffnen des
  tkinter-Fensters, EXE-Build, echte Qwen-Audioqualität der 6 Stimmen —
  auf dem Zielsystem: GUI-Probe, `--desktop-voices`, `build_windows.ps1`.

## 5a. Phase 3 (v1.3.0) — Referenz-erhaltende VD-E-Optimierung

- **122/122 Tests bestanden** (103 Bestand + 19 neue: Fachwort-
  Germanisierung, subtile Emotionen, „war"-Bug-Fix, Sampling-Variation,
  Betonungs-Ziele, Monotonie-Detektor, Referenz-Lock, Voice-Guard,
  Blindvergleich/Übernahme Ende-zu-Ende).
- Referenz-Schutz: VD-E per SHA-256-Manifest gesperrt; Apply ändert nur
  Konfigurationsschalter, nie die Stimme.
- Behobene echte Fehler: überschreibende unknown-Problemwörter-Liste,
  deutsches „war" löste somber-Emotion aus, Betonung auf negierten
  Begriffen.
- Akustische Variantenbewertung (BASE/TECH/VAR/TECHVAR) auf der
  RTX 5060: `--phase3-run` → Blindproben → `--phase3-pick` →
  `--phase3-apply`.

## 5b. Phase 2 (v1.2.0) — VoiceDesign & Prosodie

- **103/103 Tests bestanden** (86 Bestand + 17 neue: Kybalion-Text,
  neue Satzrollen, Hinweis-Budget, Anchor-Rotation, Short-Run,
  Pausenstrategien, VoiceDesign-Studio-Prüfstand, Phase-1-Schutz,
  Blindvergleich inkl. UI-Ende-zu-Ende mit Auswahl + Übernahme).
- Phase-1-Verzeichnisse durch Sentinels + harten Pfad-Check geschützt.
- Behobene echte Fehler während der Entwicklung: falscher Pfadname
  (VOICE_REFS_DIR), UI-Route im falschen HTTP-Handler, Handler-Progress-
  Attribut (Thread-Crash), Race beim Start-Flag, F0-Freigabe des
  x-Bits nach Snapshot-Wiederherstellung.
- Akustischer Vergleich (Kybalion, VoiceDesign-Modelle) auf der
  RTX 5060 auszuführen: `--phase2-run`, `--phase2-pick`, `--phase2-apply`.

## 6. Phase 1 (v1.1.0) — deutsche Optimierung

- **86/86 Tests bestanden** (60 Bestand + 26 neue GERMAN-01…10,
  Baseline-Schutz, A/B, Stimmen-Benchmark-Mechanik, gezielte
  Regeneration, harte QC-Regeln, Regressionsschutz).
- 10 Normalisierungsbugs behoben (u. a. „zweitausendein“, §-Löschung,
  „Million.“-Punkt-Rest, Ludwig XIV., Mrd.-Plural).
- Echter v1.0-Fund: JS-Syntaxfehler in app.js (`clearCache`) hätte die
  Web-UI im Browser stillgelegt — behoben + Parser-Check ergänzt.
- Akustische Endbewertung (Baseline/A-B/Stimmen) auf der RTX 5060
  ausstehend (Werkzeuge integriert, siehe PHASE1_REPORT.md §1).

## 7. Durchgeführte Optimierungsschleifen (Anforderung 59 + 82)

1. Zahlen-/Normalisierungs-Bugs behoben (Jahrhunderte, Ordinalia ≥ 20,
   Zusammenschreibung, Tausenderpunkte, URL-Queries, Minus-Zeichen,
   Zahl 10-Crash, Listen-vs-Überschrift, Absatz-Pausen).
2. Speicheroptimierung (float32 statt float64, doppelte LUFS-Messung
   entfernt, Streaming-Messung via ffmpeg, Referenzen früh freigeben) —
   10-Minuten-Text lief danach stabil in der 2-GB-Sandbox.
3. QC gehärtet (Stille-Erkennung, adaptive Sprechraten-Baseline,
   Konsistenz gegen Projektmedian).
4. Aussprache-Vorschläge entrauscht (Stopwortfilter, Akronym-Priorität).
5. UI/UX: Fortschritt inkl. QC-%, Modellade-Hinweis, Sicherheitsabfragen
   (CLEAR ALL, Löschungen), erweiterte Einstellungen eingeklappt.
