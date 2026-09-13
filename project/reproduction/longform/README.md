# Long-Form Baseline – 7 Selected Voices

Dieser Ordner wird von `project/tools/longform_benchmark.py` auf dem
RTX-5060-Windows-Host befüllt. Er enthält pro Stimme:

```
<reproduction>/longform/<voice_id>/
  input_de.txt / input_en.txt      – den Benchmark-Text (1000–1500 Wörter)
  <stem>.wav                       – die Langform-Synthese (24 kHz PCM16)
  longform_metrics.json            – Plan, Laufzeit, Segmente, QC, Warnings, SHA256
  segment_plan.json                – Segmentstatistik
```

Sowie `SUMMARY.md` mit der Gesamttabelle.

## Start (Windows RTX 5060)

Doppelklick auf `Run_LongForm.bat` im Projekt-Root (`project/Run_LongForm.bat`)
oder per PowerShell:

```powershell
# Doppelklick:
.\Run_LongForm.bat

# oder explizit:
.\.venv\Scripts\python.exe .\tools\longform_benchmark.py
```

## Was das Skript macht

- Bevorzugt die bereits erzeugten Qwen-VoiceDesign-Referenz-WAVs unter
  `cache/voice_refs/<voice_id>.wav` (aus `reproduce_premium.py`-Läufen).
- Fallback auf die im Registry-Eintrag konfigurierte Audition-MP3, die
  automatisch über ffmpeg einmalig nach `cache/voice_refs/_converted/`
  als 24 kHz Mono WAV transkodiert wird (erster Start).
- VoiceDesign wird **nicht** neu ausgeführt, solange eine Referenz
  vorhanden ist (kein `--allow-design` ohne ausdrücklichen Wunsch).
- Verwendet den Produktions-Pipeline-Pfad (Normalisierung → Aussprache
  → Segmentierung → QC → Assembler → EBU R128-Mastering).
- Pro Stimme wird genau **ein** `VoiceCloneEngine` erstellt; der
  Clone-Prompt wird einmal in `_ensure_prompt()` gebaut und über alle
  Segmente wiederverwendet (kein Prompt-Neubau pro Segment).
- Sampling ist fest auf `balanced` (`temperature=0.7, top_k=50, top_p=0.9,
  repetition_penalty=1.05`).
- Segment-Seeds werden deterministisch per sha256(Cache-Key) abgeleitet
  (statt über Pythons nicht-stabiles `hash()`), sodass Läufe
  reproduzierbar sind.

## Keine Produktion – nur Baseline

Das Skript erzeugt die Langform-WAVs für einen menschlichen
Hörvergleich. Es nimmt **keine** endgültige Voice-Auswahl vor und
verändert keine Rezepte/Seeds.
