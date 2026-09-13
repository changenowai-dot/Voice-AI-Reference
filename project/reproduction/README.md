# Reproduction Outputs (local RTX 5060 runs)

Dieser Ordner enthält die **REPRODUCED**-Ausgaben lokaler Qwen VoiceDesign→Clone-Läufe
via `project/tools/reproduce_premium.py` (PowerShell-Einstiege:
`project/tools/reproduce_premium.ps1` für Einzelaufrufe;
`project/tools/reproduce_batch.ps1` für sequentiellen Batch-Betrieb mit
pro-Voice-Subprocess-Isolation — empfohlen für RTX 5060 8 GB).

## Unterstützte Stimmen (EN + DE)

Insgesamt 11 Premium-Stimmen können reproduziert werden (Prioritätsreihenfolge
Englisch zuerst, dann Deutsch):

1. voice-09  en_male_warm_storytelling_authoritative_02 (EN, seed 52018) — locked
2. voice-12  en_male_velvet_baritone_01                 (EN, seed 52021) — locked
3. voice-22  en_male_deep_authoritative_scholar_01      (EN, seed 52031)
4. voice-23  en_male_mature_documentary_natural_01      (EN, seed 52032)
5. voice-24  en_male_deep_clear_insightful_01           (EN, seed 52033)
6. voice-25  en_male_warm_grounded_humanist_01          (EN, seed 52034)
7. voice-27  en_male_extremely_natural_deep_conversational_01 (EN, seed 52036)
8. voice-30  de_male_warm_storytelling_authoritative_01 (DE, seed 53003)
9. voice-32  de_male_deep_natural_conversational_01     (DE, seed 53005)
10. voice-33 de_female_deep_warm_documentary_01         (DE, seed 53011)
11. voice-34 de_female_deep_calm_intelligent_01         (DE, seed 53012) — good_archived; wird reproduziert, aber der Status im Rezept wird **nie** automatisch promoted.

Deutsche Stimmen nutzen den deutschen VoiceDesign-Referenztext aus
`app/prosody/instruct.py:VOICEDESIGN_REF_TEXT_DE` und den deutschen
Auditionstext aus dem Rezept ("Jede Entdeckung beginnt mit einer Frage…").

## Layout pro Stimme

```
project/reproduction/<voice_id>/
    reference_voicedesign.wav   — Archivkopie der Qwen VoiceDesign-Referenz
                                 (Original in cache/voice_refs/<voice_id>.wav)
    clone_prompt.json          — Metadaten zum Clone-Prompt (SHA256 der Referenz,
                                 Referenztext, Erzeugungszeitpunkt)
    test_short.wav             — Kurztest mit dem VoiceDesign-Referenztext (~15s)
    test_audition.wav          — Kurztest mit dem sprachpassenden Audition-
                                 Vergleichstext (EN/DE)
    test_long.wav              — (optional) Langer Testtext
    manifest.json              — Vollständige Provenienz + SHA256 + Laufzeitinfos
```

Alle erzeugten Dateien sind **REPRODUCED** — keine Datei hier wird als
`ORIGINAL_RECOVERED` bezeichnet. Die originalen Audition-MP3s (Arena-TTS,
von Menschen bewertet) liegen unter `project/benchmark/fast_audition/`
und `project/benchmark/fast_audition_de/` und werden nie überschrieben.

Bereits komplett reproduzierte Stimmen (Status=REPRODUCED, Seed/Sprache/
Referenztext stimmen mit dem Rezept überein) werden im Batch-Betrieb
automatisch übersprungen, damit bereits erfolgreiche Outputs (z. B. voice-09
und voice-12) nicht angetastet werden.

Die Golden Reference `project/VD-E_GOLDEN_REFERENCE/VD-E.wav` (SHA256
`B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025`) wird von
diesem Workflow nicht berührt und bei jedem Validate-Lauf gegengeprüft.

## Typische Aufrufe (PowerShell 5.1, Windows)

```powershell
# 1. Setup (einmalig):
powershell -ExecutionPolicy Bypass -File project\SETUP.ps1

# 2. Plan anzeigen (keine GPU):
powershell -ExecutionPolicy Bypass -File project\tools\reproduce_batch.ps1 -DryRun

# 3. Die 9 verbleibenden Shortlist-Stimmen (EN→DE) sequentiell im
#    Subprocess-Batch-Modus mit anschliessender Validierung:
powershell -ExecutionPolicy Bypass -File project\tools\reproduce_batch.ps1

# 4. Nur Validierung nach einem Lauf:
python project\tools\reproduce_premium.py --validate --remaining
```
