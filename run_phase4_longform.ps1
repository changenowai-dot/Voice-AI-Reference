# ============================================================
# VoiceOverApp Phase 4 — Long-Form Benchmark Runner
# ============================================================
# Führt Long-Form-Tests mit dem A/B-Gewinner durch.
#
# VORAUSSETZUNG: Phase 4 Benchmark bereits abgeschlossen
#
# AUSFÜHRUNG:
#   .\run_phase4_longform.ps1 -Winner D -MaxMinutes 60
#   .\run_phase4_longform.ps1 -Winner D -MaxMinutes 120
#   .\run_phase4_longform.ps1 -Winner A -Quick
#
# ============================================================

param(
    [string]$Winner = "A",
    [int]$MaxMinutes = 60,
    [switch]$Quick,
    [string]$RunID = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

if (-not $RunID) {
    $RunID = Get-Date -Format "yyyyMMdd_HHmmss"
}

$ResultsDir = Join-Path $PSScriptRoot "results\phase4\longform_$RunID"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "VoiceOverApp Phase 4 — Long-Form Benchmark" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Winner: $Winner" -ForegroundColor Gray
Write-Host "Max Duration: $MaxMinutes minutes" -ForegroundColor Gray
Write-Host "Run-ID: $RunID" -ForegroundColor Gray
Write-Host "Results: $ResultsDir" -ForegroundColor Gray
Write-Host ""

New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null

# ============================================================
# Golden Reference Verify
# ============================================================
$GoldenRef = Join-Path $PSScriptRoot "reference\VD-E_GOLDEN_REFERENCE\VD-E.wav"
$ExpectedHash = "B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025"

if (-not (Test-Path $GoldenRef)) {
    Write-Host "FEHLER: Golden Reference nicht gefunden" -ForegroundColor Red
    exit 1
}

$ActualHash = (Get-FileHash $GoldenRef -Algorithm SHA256).Hash.ToUpper()
if ($ActualHash -ne $ExpectedHash) {
    Write-Host "FEHLER: Golden Reference Hash-Mismatch!" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Golden Reference verifiziert" -ForegroundColor Green

# Runtime Voice Reference prüfen
$RuntimeRef = Join-Path $PSScriptRoot "cache\voice_refs\VD-E.wav"
if (-not (Test-Path $RuntimeRef)) {
    Write-Host "Runtime Voice Reference fehlt. Kopiere..." -ForegroundColor DarkYellow
    New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot "cache\voice_refs") | Out-Null
    Copy-Item $GoldenRef $RuntimeRef -Force
    Write-Host "✓ Runtime Voice Reference erstellt" -ForegroundColor Green
} else {
    Write-Host "✓ Runtime Voice Reference vorhanden" -ForegroundColor Green
}

Write-Host ""

# ============================================================
# Long-Form Test ausführen
# ============================================================
$LongformScript = Join-Path $PSScriptRoot "benchmark\phase4_longform.py"

if (-not (Test-Path $LongformScript)) {
    Write-Host "FEHLER: $LongformScript nicht gefunden" -ForegroundColor Red
    exit 1
}

$LongformArgs = @("--winner", $Winner, "--max-minutes", $MaxMinutes)
if ($Quick) {
    $LongformArgs += "--quick"
}

Write-Host "Starte Long-Form-Test..." -ForegroundColor Yellow
Write-Host "Parameter: winner=$Winner, max-minutes=$MaxMinutes, quick=$Quick" -ForegroundColor Gray
Write-Host ""

$LongformOutput = Join-Path $ResultsDir "longform_output.txt"
$StartTime = Get-Date

python $LongformScript @LongformArgs *> $LongformOutput
$ExitCode = $LASTEXITCODE

$EndTime = Get-Date
$TotalTime = ($EndTime - $StartTime).TotalMinutes

# Reports kopieren
$ReportMd = Join-Path $PSScriptRoot "PHASE4_LONGFORM_REPORT.md"
$ReportJson = Join-Path $PSScriptRoot "PHASE4_LONGFORM_REPORT.json"

if (Test-Path $ReportMd) {
    Copy-Item $ReportMd (Join-Path $ResultsDir "PHASE4_LONGFORM_REPORT.md") -Force
}
if (Test-Path $ReportJson) {
    Copy-Item $ReportJson (Join-Path $ResultsDir "PHASE4_LONGFORM_REPORT.json") -Force
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan

if ($ExitCode -eq 0) {
    Write-Host "LONG-FORM BENCHMARK ABGESCHLOSSEN" -ForegroundColor Green
    Write-Host "Gesamtlaufzeit: $([math]::Round($TotalTime, 1)) Minuten" -ForegroundColor Gray
    Write-Host "Results: $ResultsDir" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Audio-Dateien:" -ForegroundColor White
    Write-Host "  - output/phase4_longform_5min/" -ForegroundColor Gray
    Write-Host "  - output/phase4_longform_10min/" -ForegroundColor Gray
    Write-Host "  - output/phase4_longform_30min/" -ForegroundColor Gray
    if (-not $Quick -and $MaxMinutes -ge 60) {
        Write-Host "  - output/phase4_longform_60min/" -ForegroundColor Gray
    }
    if (-not $Quick -and $MaxMinutes -ge 120) {
        Write-Host "  - output/phase4_longform_120min/" -ForegroundColor Gray
    }
} else {
    Write-Host "LONG-FORM BENCHMARK FEHLGESCHLAGEN" -ForegroundColor Red
    Write-Host "Output: $LongformOutput" -ForegroundColor Red
    Get-Content $LongformOutput -Tail 30
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan

exit $ExitCode
