# ============================================================
# VoiceOverApp Phase 4 — Target Hardware Runner
# ============================================================
# Führt den kompletten Audio-Benchmark auf der Zielhardware aus.
# 
# VORAUSSETZUNGEN:
# - Windows 10/11
# - Python 3.10-3.13
# - NVIDIA GPU mit CUDA
# - PyTorch mit CUDA-Support
# - qwen-tts installiert
# - FFmpeg verfügbar
#
# AUSFÜHRUNG:
#   .\run_phase4_target.ps1
#
# OUTPUT:
#   results/phase4/<timestamp>/
#     - environment.json
#     - baseline/
#     - variant_A/ ... variant_E/
#     - AUDIO_REVIEW.md
#     - PHASE4_REAL_AUDIO_REPORT.md
#     - PHASE4_REAL_AUDIO_REPORT.json
#
# ============================================================

param(
    [switch]$SkipEnvCheck,
    [switch]$SkipBaseline,
    [switch]$SkipABTest,
    [switch]$Quick
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Timestamp für eindeutige Run-ID
$RunID = Get-Date -Format "yyyyMMdd_HHmmss"
$ResultsDir = Join-Path $PSScriptRoot "results\phase4\$RunID"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "VoiceOverApp Phase 4 — Target Hardware Benchmark" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Run-ID: $RunID" -ForegroundColor Gray
Write-Host "Results: $ResultsDir" -ForegroundColor Gray
Write-Host ""

# Results-Verzeichnis erstellen
New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null

# ============================================================
# Schritt 1: Environment Check
# ============================================================
Write-Host "Schritt 1/6: Environment Check..." -ForegroundColor Yellow

$EnvReport = Join-Path $ResultsDir "environment.json"
$EnvCheckScript = Join-Path $PSScriptRoot "benchmark\phase4_env_check.py"

if (-not (Test-Path $EnvCheckScript)) {
    Write-Host "FEHLER: $EnvCheckScript nicht gefunden" -ForegroundColor Red
    exit 1
}

if (-not $SkipEnvCheck) {
    $EnvOutput = Join-Path $ResultsDir "env_check_output.txt"
    python $EnvCheckScript *> $EnvOutput
    $EnvExitCode = $LASTEXITCODE
    
    if ($EnvExitCode -ne 0) {
        Write-Host ""
        Write-Host "UMGEBUNGS-CHECK FEHLGESCHLAGEN" -ForegroundColor Red
        Write-Host "Bitte Output prüfen: $EnvOutput" -ForegroundColor Red
        Write-Host ""
        Get-Content $EnvOutput
        Write-Host ""
        Write-Host "Alle Voraussetzungen müssen erfüllt sein." -ForegroundColor Red
        Write-Host "Siehe PHASE4_INSTRUCTIONS.md für Details." -ForegroundColor Red
        exit 1
    }
    
    # JSON-Report kopieren
    $EnvJson = Join-Path $PSScriptRoot "benchmark\phase4_env_check.json"
    if (Test-Path $EnvJson) {
        Copy-Item $EnvJson $EnvReport -Force
    }
    
    Write-Host "✓ Environment OK" -ForegroundColor Green
} else {
    Write-Host "⚠ Environment-Check übersprungen" -ForegroundColor DarkYellow
}

Write-Host ""

# ============================================================
# Schritt 2: Golden Reference Check
# ============================================================
Write-Host "Schritt 2/6: Golden Reference Check..." -ForegroundColor Yellow

$GoldenRef = Join-Path $PSScriptRoot "reference\VD-E_GOLDEN_REFERENCE\VD-E.wav"
$ExpectedHash = "B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025"

if (-not (Test-Path $GoldenRef)) {
    Write-Host "FEHLER: Golden Reference nicht gefunden: $GoldenRef" -ForegroundColor Red
    exit 1
}

$ActualHash = (Get-FileHash $GoldenRef -Algorithm SHA256).Hash.ToUpper()
if ($ActualHash -ne $ExpectedHash) {
    Write-Host "FEHLER: Golden Reference Hash-Mismatch!" -ForegroundColor Red
    Write-Host "Erwartet: $ExpectedHash" -ForegroundColor Red
    Write-Host "Gefunden: $ActualHash" -ForegroundColor Red
    Write-Host "Golden Reference wurde verändert. Abbruch." -ForegroundColor Red
    exit 1
}

Write-Host "✓ Golden Reference Hash: $ActualHash" -ForegroundColor Green
Write-Host ""

# ============================================================
# Schritt 3: Runtime Voice Reference Setup
# ============================================================
Write-Host "Schritt 3/6: Runtime Voice Reference Setup..." -ForegroundColor Yellow

$RuntimeRefDir = Join-Path $PSScriptRoot "cache\voice_refs"
$RuntimeRef = Join-Path $RuntimeRefDir "VD-E.wav"

if (-not (Test-Path $RuntimeRef)) {
    Write-Host "Runtime Voice Reference fehlt. Kopiere Golden Reference..." -ForegroundColor DarkYellow
    New-Item -ItemType Directory -Force -Path $RuntimeRefDir | Out-Null
    Copy-Item $GoldenRef $RuntimeRef -Force
    
    # Hash prüfen
    $RuntimeHash = (Get-FileHash $RuntimeRef -Algorithm SHA256).Hash.ToUpper()
    if ($RuntimeHash -ne $ExpectedHash) {
        Write-Host "FEHLER: Runtime Voice Reference Hash-Mismatch nach Kopie!" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "✓ Runtime Voice Reference erstellt: $RuntimeRef" -ForegroundColor Green
} else {
    $RuntimeHash = (Get-FileHash $RuntimeRef -Algorithm SHA256).Hash.ToUpper()
    if ($RuntimeHash -ne $ExpectedHash) {
        Write-Host "FEHLER: Runtime Voice Reference Hash-Mismatch!" -ForegroundColor Red
        Write-Host "Erwartet: $ExpectedHash" -ForegroundColor Red
        Write-Host "Gefunden: $RuntimeHash" -ForegroundColor Red
        Write-Host "Runtime Voice Reference wurde verändert." -ForegroundColor Red
        exit 1
    }
    Write-Host "✓ Runtime Voice Reference vorhanden: $RuntimeRef" -ForegroundColor Green
}

Write-Host ""

# ============================================================
# Schritt 4: Baseline
# ============================================================
Write-Host "Schritt 4/6: Production Baseline..." -ForegroundColor Yellow

if (-not $SkipBaseline) {
    Write-Host "Erzeuge Baseline-Audio..." -ForegroundColor Gray
    
    $BaselineScript = Join-Path $PSScriptRoot "benchmark\phase4_benchmark.py"
    if (-not (Test-Path $BaselineScript)) {
        Write-Host "FEHLER: $BaselineScript nicht gefunden" -ForegroundColor Red
        exit 1
    }
    
    # Benchmark-Skript ausführen (erzeugt Baseline + A/B-Test)
    $BenchmarkOutput = Join-Path $ResultsDir "benchmark_output.txt"
    
    if ($SkipABTest) {
        Write-Host "⚠ A/B-Test übersprungen (nur Baseline)" -ForegroundColor DarkYellow
        # Hier könnte man ein separates Baseline-only-Skript aufrufen
        # Für jetzt: Vollständiger Benchmark
    }
    
    python $BenchmarkScript *> $BenchmarkOutput
    $BenchmarkExitCode = $LASTEXITCODE
    
    if ($BenchmarkExitCode -ne 0) {
        Write-Host ""
        Write-Host "BENCHMARK FEHLGESCHLAGEN" -ForegroundColor Red
        Write-Host "Bitte Output prüfen: $BenchmarkOutput" -ForegroundColor Red
        Write-Host ""
        Get-Content $BenchmarkOutput -Tail 50
        exit 1
    }
    
    # Reports kopieren
    $ReportMd = Join-Path $PSScriptRoot "PHASE4_REAL_AUDIO_REPORT.md"
    $ReportJson = Join-Path $PSScriptRoot "PHASE4_REAL_AUDIO_REPORT.json"
    
    if (Test-Path $ReportMd) {
        Copy-Item $ReportMd (Join-Path $ResultsDir "PHASE4_REAL_AUDIO_REPORT.md") -Force
    }
    if (Test-Path $ReportJson) {
        Copy-Item $ReportJson (Join-Path $ResultsDir "PHASE4_REAL_AUDIO_REPORT.json") -Force
    }
    
    Write-Host "✓ Baseline + A/B-Test abgeschlossen" -ForegroundColor Green
} else {
    Write-Host "⚠ Baseline übersprungen" -ForegroundColor DarkYellow
}

Write-Host ""

# ============================================================
# Schritt 5: AUDIO_REVIEW.md Template erstellen
# ============================================================
Write-Host "Schritt 5/6: AUDIO_REVIEW.md Template..." -ForegroundColor Yellow

$AudioReview = Join-Path $ResultsDir "AUDIO_REVIEW.md"

$ReviewContent = @"
# Audio Review — Phase 4 Benchmark

**Run-ID:** $RunID
**Datum:** $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

---

## Bewertungsanleitung

Bitte jede Variante anhören und bewerten (0-10):

- **0-3:** Unbrauchbar (starke Artefakte, falsche Stimme, unverständlich)
- **4-6:** Akzeptabel (hörbare Probleme, aber nutzbar)
- **7-8:** Gut (minor Probleme, insgesamt überzeugend)
- **9-10:** Exzellent (professionelle Qualität, keine hörbaren Probleme)

---

## Baseline

| Kriterium | Wert |
|-----------|------|
| Voice Identity | ?/10 |
| Naturalness | ?/10 |
| Pronunciation | ?/10 |
| Prosody | ?/10 |
| Continuity | ?/10 |
| Long-Form Stability | ?/10 |
| **Overall** | **?/10** |

**Notizen:**
- 
- 
- 

---

## Variante A (Production-Standard, 420 Zeichen)

| Kriterium | Wert |
|-----------|------|
| Voice Identity | ?/10 |
| Naturalness | ?/10 |
| Pronunciation | ?/10 |
| Prosody | ?/10 |
| Continuity | ?/10 |
| Artifacts | ?/10 |
| **Overall** | **?/10** |

**Notizen:**
- 
- 

---

## Variante B (Larger Segments, 700 Zeichen)

| Kriterium | Wert |
|-----------|------|
| Voice Identity | ?/10 |
| Naturalness | ?/10 |
| Pronunciation | ?/10 |
| Prosody | ?/10 |
| Continuity | ?/10 |
| Artifacts | ?/10 |
| **Overall** | **?/10** |

**Notizen:**
- 
- 

---

## Variante C (Very Large Blocks, 1200 Zeichen)

| Kriterium | Wert |
|-----------|------|
| Voice Identity | ?/10 |
| Naturalness | ?/10 |
| Pronunciation | ?/10 |
| Prosody | ?/10 |
| Continuity | ?/10 |
| Artifacts | ?/10 |
| **Overall** | **?/10** |

**Notizen:**
- 
- 

---

## Variante D (Large Blocks + Cutting)

| Kriterium | Wert |
|-----------|------|
| Voice Identity | ?/10 |
| Naturalness | ?/10 |
| Pronunciation | ?/10 |
| Prosody | ?/10 |
| Continuity | ?/10 |
| Artifacts | ?/10 |
| **Overall** | **?/10** |

**Notizen:**
- 
- 

---

## Variante E (Hybrid, 1000 Zeichen)

| Kriterium | Wert |
|-----------|------|
| Voice Identity | ?/10 |
| Naturalness | ?/10 |
| Pronunciation | ?/10 |
| Prosody | ?/10 |
| Continuity | ?/10 |
| Artifacts | ?/10 |
| **Overall** | **?/10** |

**Notizen:**
- 
- 

---

## Gewinner

**Variante:** ?

**Begründung:**
- 
- 
- 

---

## Long-Form Ergebnisse

| Dauer | OK | Dauer (s) | Segmente | QC-Score | Konsistenz | Notizen |
|-------|----|-----------|----------|----------|------------|---------|
| 5 min | ? | ? | ? | ? | ? | |
| 10 min | ? | ? | ? | ? | ? | |
| 30 min | ? | ? | ? | ? | ? | |
| 60 min | ? | ? | ? | ? | ? | |
| 120 min | ? | ? | ? | ? | ? | |

---

## Fazit

**Empfehlung für Production:**
- 
- 
- 

**Nächste Schritte:**
- 
- 
- 
"@

$ReviewContent | Out-File -FilePath $AudioReview -Encoding UTF8
Write-Host "✓ AUDIO_REVIEW.md erstellt: $AudioReview" -ForegroundColor Green
Write-Host "  Bitte nach Benchmark manuell ausfüllen." -ForegroundColor Gray

Write-Host ""

# ============================================================
# Schritt 6: Zusammenfassung
# ============================================================
Write-Host "Schritt 6/6: Zusammenfassung..." -ForegroundColor Yellow
Write-Host ""

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "BENCHMARK ABGESCHLOSSEN" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Run-ID: $RunID" -ForegroundColor Gray
Write-Host "Results: $ResultsDir" -ForegroundColor Gray
Write-Host ""
Write-Host "Erzeugte Dateien:" -ForegroundColor White
Write-Host "  - environment.json" -ForegroundColor Gray
Write-Host "  - env_check_output.txt" -ForegroundColor Gray
Write-Host "  - benchmark_output.txt" -ForegroundColor Gray
Write-Host "  - PHASE4_REAL_AUDIO_REPORT.md" -ForegroundColor Gray
Write-Host "  - PHASE4_REAL_AUDIO_REPORT.json" -ForegroundColor Gray
Write-Host "  - AUDIO_REVIEW.md (manuell ausfüllen)" -ForegroundColor Gray
Write-Host ""
Write-Host "Audio-Dateien:" -ForegroundColor White
Write-Host "  - output/phase4_baseline/" -ForegroundColor Gray
Write-Host "  - output/phase4_A/ ... output/phase4_E/" -ForegroundColor Gray
Write-Host ""
Write-Host "Nächste Schritte:" -ForegroundColor Yellow
Write-Host "  1. Audio-Dateien anhören" -ForegroundColor White
Write-Host "  2. AUDIO_REVIEW.md ausfüllen" -ForegroundColor White
Write-Host "  3. Gewinner identifizieren" -ForegroundColor White
Write-Host "  4. Long-Form-Test (optional):" -ForegroundColor White
Write-Host "     python benchmark/phase4_longform.py --winner [A|B|C|D|E]" -ForegroundColor Gray
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
