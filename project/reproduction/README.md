# Reproduction Outputs (local RTX 5060 runs)

Dieser Ordner enthält die **REPRODUCED**-Ausgaben lokaler Qwen VoiceDesign→Clone-Läufe
via `project/tools/reproduce_premium.py` (PowerShell-Einstieg:
`project/tools/reproduce_premium.ps1`).

## Layout pro Stimme

```
project/reproduction/<voice_id>/
    reference_voicedesign.wav   — Archivkopie der Qwen VoiceDesign-Referenz
                                 (Original in cache/voice_refs/<voice_id>.wav)
    clone_prompt.json          — Metadaten zum Clone-Prompt (SHA256 der Referenz,
                                 Referenztext, Erzeugungszeitpunkt)
    test_short.wav             — Kurztest mit dem VoiceDesign-Referenztext (~15s)
    test_audition.wav          — Kurztest mit dem Audition-Vergleichstext
    test_long.wav              — (optional) Langer Testtext
    manifest.json              — Vollständige Provenienz + SHA256 + Laufzeitinfos
```

Alle erzeugten Dateien sind **REPRODUCED** — keine Datei hier wird als
`ORIGINAL_RECOVERED` bezeichnet. Die originalen Audition-MP3s (Arena-TTS,
von Menschen bewertet) liegen unter `project/benchmark/fast_audition/`
und `project/benchmark/fast_audition_round02/` und werden nie überschrieben.

Die Golden Reference `project/VD-E_GOLDEN_REFERENCE/VD-E.wav` wird von diesem
Workflow nicht berührt.
