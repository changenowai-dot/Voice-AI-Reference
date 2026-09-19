# Phase 4 Benchmark — Ausführungsanleitung

## VORAUSSETZUNGEN

Dieser Benchmark MUSS auf der echten Zielhardware ausgeführt werden:
- AMD Ryzen 7 5700X
- 32 GB RAM
- NVIDIA RTX 5060 (8 GB VRAM)
- Windows 10 x64
- Python 3.10-3.13
- PyTorch 2.11+cu128
- qwen-tts 0.1.1
- FFmpeg

## SCHRITT 1: Umgebung prüfen

```powershell
cd VoiceOverApp
python benchmark/phase4_env_check.py
```

Dieses Skript prüft alle Voraussetzungen und erstellt einen
Umgebungsbericht. Es muss ALLE Checks bestehen.

## SCHRITT 2: Runtime Voice Reference setup

```powershell
# Golden Reference → Runtime kopieren
New-Item -ItemType Directory -Force -Path "cache\voice_refs"
Copy-Item "reference\VD-E_GOLDEN_REFERENCE\VD-E.wav" "cache\voice_refs\VD-E.wav"

# Hash verifizieren
(Get-FileHash "cache\voice_refs\VD-E.wav" -Algorithm SHA256).Hash
# Erwartet: B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025
```

## SCHRITT 3: Baseline + A/B-Test ausführen

```powershell
python benchmark/phase4_benchmark.py
```

Dieses Skript führt automatisch durch:
1. Baseline-Audio erzeugen (Production-Parameter)
2. Golden Reference Vergleich
3. 5 Segmentierungs-Varianten (A, B, C, D, E)
4. Voice-Consistency prüfen
5. Segment-Continuity prüfen
6. Alle Metriken sammeln
7. Report generieren

**Erwartete Laufzeit:** 30-90 Minuten

## SCHRITT 4: Long-Form-Test

```powershell
python benchmark/phase4_longform.py
```

Testet die beste Variante aus dem A/B-Test mit:
- 5 Minuten Text
- 10 Minuten Text
- 30 Minuten Text
- 60 Minuten Text (wenn VRAM reicht)
- 120 Minuten Text (wenn stabil)

## SCHRITT 5: Akustische Bewertung

Die erzeugten WAV-Dateien in `output/phase4_*/` anhören und
die Bewertungstabelle in `PHASE4_REAL_AUDIO_REPORT.md` ausfüllen.

## OUTPUT

- `PHASE4_REAL_AUDIO_REPORT.md` — Vollständiger Report
- `PHASE4_REAL_AUDIO_REPORT.json` — Maschinell lesbar
- `output/phase4_baseline/` — Baseline-Audio
- `output/phase4_A/` ... `output/phase4_E/` — A/B-Varianten
- `output/phase4_longform/` — Long-Form-Tests
