# START-ANLEITUNG — KORREKTUR (VoiceOverApp 2.0.0)

> **Gültigkeitsbereich:** Diese Datei korrigiert ausschließlich die
> **Startbeschreibung**. Alle Informationen über **VD-E** und den
> **Produktionskern** (Referenz `cache\voice_refs\VD-E.wav`,
> SHA256 `B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025`,
> gesperrte Produktionsparameter) bleiben unverändert gültig.

Falls die bestehende Datei `VoiceOverApp_VD-E_FINAL_Anleitung.pdf` einen
Start über **Browser / Webserver / Port 8750** beschreibt, gilt ab
Version 2.0.0 stattdessen:

## Richtiger Start (nur diese Schritte)

1. **Doppelklick auf `VoiceOverApp.bat`**
   (oder auf die gebaute `VoiceOverApp.exe` in `dist\VoiceOverApp\`)
2. Es öffnet sich **direkt die Desktop-App** (echtes Fenster) —
   **kein Browser, kein Webserver, kein Port 8750**.
3. PDF in das Fenster ziehen → Sprache (Deutsch/English) und Stimme
   wählen (VD-E ist Standard) → **„VOICE-OVER ERSTELLEN“** klicken.
4. Fortschritt beobachten → fertig: **WAV öffnen / MP3 öffnen /
   Ordner öffnen / Bericht öffnen**.

## Für Entwickler (optional)

```powershell
.\VoiceOverApp.bat                                  # Desktop-GUI
.\START.ps1                                         # Desktop-GUI
.\START.ps1 -Headless -Files "input\text.txt"       # CLI-Pipeline
.venv\Scripts\python.exe app\main.py --headless --files "input.txt"
.venv\Scripts\python.exe app\main.py --webserver    # nur explizit (alt)
```

## Was sich NICHT geändert hat

- VD-E-Produktionsstimme: unverändert, gesperrt (Identity-Lock prüft
  den SHA256 bei jedem Start).
- Pipeline: Segmentierung, TTS, Aussprache, QC, Regeneration, Cache,
  Resume, Assembly, Mastering — identisch.
- Ausgaben: WAV (24 bit/48 kHz) + MP3 320 kbps, YouTube-Mastering.

---
*Technischer Hintergrund: Der frühere Standardstart führte über
`START.bat → START.ps1 → app\main.py` ohne Argumente in den lokalen
Webserver (Browser, Port 8750). Ab 2.0.0 starten `START.bat`,
`START.ps1`, `VoiceOverApp.bat`, `desktop.py` und die EXE durchgehend
die Tkinter-Desktop-GUI; der Webserver ist nur noch explizit über
`--webserver` erreichbar.*
