# TOP-3 Long-Form Real Run

Dedizierter Testlauf fuer die drei vom Benutzer nach menschlichem
Hoervergleich ausgewaehlten Stimmen:

1. `de_female_warm_empathetic_01` — persoenlicher Favorit
2. `de_female_deep_warm_documentary_01`
3. `en_male_warm_grounded_humanist_01`

## Start auf dem RTX-5060-Windows-Host

Im Projekt-Verzeichnis (`...\\project\\`) doppelklicken:

```
Run_TOP3_LongForm.bat
```

Das ruft intern auf:

```
tools\longform_benchmark.py --top3 --fresh
```

* `--top3` — nur die drei oben genannten Stimmen; Default-Ausgabeordner
  `project\reproduction\TOP3_LONGFORM_REAL\`.
* `--fresh` — **Segment-Audio-Cache ist fuer diesen Lauf deaktiviert**
  (`advanced.cache_enabled = False`), sodass jedes Segment wirklich neu
  synthetisiert wird. Referenz-WAVs / VoiceClone-Prompts werden weiter
  verwendet; der bestehende Segment-Cache der 7-Voice-Baseline bleibt
  unberuehrt.

Zusaetzliche Kommandozeilenargumente werden durch `%*` an das Python-Skript
durchgereicht (z.B. `Run_TOP3_LongForm.bat --allow-design`).

## Erwartete Konsolen-Ausgabe

* `===== (1/3) de_female_warm_empathetic_01 =====` …
  `(3/3) en_male_warm_grounded_humanist_01` — **genau 3 Stimmen**,
  kein `(…/7)`.
* Pro Stimme: `reused=0`, `regenerated ~ n_segments`, `failed=0`.
* Am Ende ExitCode `0`; ExitCode `2` bedeutet: Cache-Reuse wurde trotz
  `--fresh` erkannt — in diesem Fall nicht als erfolgreich werten.

## Ausgabestruktur

```
project/reproduction/TOP3_LONGFORM_REAL/
    SUMMARY.md                         kompakte Tabellenansicht (inkl. NeuGen=JA/NEIN)
    run_summary.json                   maschinenlesbar
    <voice_id>/
        input_de.txt | input_en.txt    verwendeter Benchmark-Text
        <voice_id>.wav                  fertige Long-Form-WAV (24 kHz, PCM16, LUFS-mastered)
        longform_metrics.json          Segmente/Dauer/Score/WAV-SHA256/...
        segment_plan.json              Segment-Statistik
```

## Schutzgarantien

* Golden Reference `VD-E.wav` (SHA256
  `b156c02a60a873ad95fc92390c4a136c85308b20188373cd734bee5e5e5f2025`)
  wird nicht beruehrt.
* Bestehende Rezepte, Sampling-Parameter, Seeds, Segmentierung, QC-Schwellen
  und Audio-Mastering-Logik sind unveraendert.
* Die 7-Voice-Baseline unter `project\reproduction\longform\` sowie deren
  Cache werden **nicht** geloescht oder ueberschrieben.
* Die anderen vier Stimmen bleiben als Reserve erhalten.
* Die normale App (`START.bat`) ist von diesem Lauf vollstaendig unabhaengig.
