# ============================================================
# VoiceOverApp Phase 4 - Long-Form Benchmark Runner
# ============================================================
#
# AUSFUEHRUNG:
#   .\run_phase4_longform.ps1 -Winner D -MaxMinutes 60
#
# ============================================================

param(
    [ValidateSet("A","B","C","D","E")]
    [string]$Winner = "A",
    [int]$MaxMinutes = 60,
    [switch]$Quick,
    [string]$RunID = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# ============================================================
# Repository Root erkennen
# ============================================================
$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

$RepoRoot = $ScriptDir
$ProjectRoot = Join-Path $RepoRoot "project"

# Validierung
if (-not (Test-Path (Join-Path $ProjectRoot "app"))) {
    Write-Host "FEHLER: Projektstruktur nicht gefunden." -ForegroundColor Red
    Write-Host "Erwartet: $ProjectRoot\app\" -ForegroundColor Red
    exit 1
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "VoiceOverApp Phase 4 - Long-Form Benchmark" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Repository: $RepoRoot" -ForegroundColor Gray
Write-Host "Project:    $ProjectRoot" -ForegroundColor Gray

if (-not $RunID) {
    $RunID = Get-Date -Format "yyyyMMdd_HHmmss"
}

$ResultsDir = Join-Path $RepoRoot "results\phase4\longform_$RunID"
Write-Host "Winner:   $Winner" -ForegroundColor Gray
Write-Host "Max:      $MaxMinutes minutes" -ForegroundColor Gray
Write-Host "Run-ID:   $RunID" -ForegroundColor Gray
Write-Host "Results:  $ResultsDir" -ForegroundColor Gray
Write-Host ""

New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null

# ============================================================
# Python pruefen
# ============================================================
$PythonCmd = $null
$pythonCandidates = @("python", "python3", "py")
foreach ($py in $pythonCandidates) {
    try {
        $ver = & $py --version 2>&1
        if ($LASTEXITCODE -eq 0 -and $ver -match "Python 3\.") {
            $PythonCmd = $py
            break
        }
    }
    catch {
        # Weiter probieren
    }
}

if (-not $PythonCmd) {
    Write-Host "FEHLER: Python 3 nicht gefunden." -ForegroundColor Red
    exit 1
}

# ============================================================
# Golden Reference Verify
# ============================================================
Write-Host "Schritt 1/4: Golden Reference..." -ForegroundColor Yellow

$GoldenRef = Join-Path $RepoRoot "reference\VD-E_GOLDEN_REFERENCE\VD-E.wav"
$ExpectedHash = "B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025"

if (-not (Test-Path $GoldenRef)) {
    Write-Host "  FEHLER: Golden Reference nicht gefunden" -ForegroundColor Red
    exit 1
}

$ActualHash = (Get-FileHash $GoldenRef -Algorithm SHA256).Hash.ToUpper()
if ($ActualHash -ne $ExpectedHash) {
    Write-Host "  FEHLER: Golden Reference Hash-Mismatch!" -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] Golden Reference verifiziert" -ForegroundColor Green

# ============================================================
# Runtime Voice Reference
# ============================================================
Write-Host "Schritt 2/4: Runtime Voice Reference..." -ForegroundColor Yellow

$RuntimeRefDir = Join-Path $ProjectRoot "cache\voice_refs"
$RuntimeRef = Join-Path $RuntimeRefDir "VD-E.wav"

if (-not (Test-Path $RuntimeRef)) {
    Write-Host "  Runtime Voice Reference fehlt. Kopiere..." -ForegroundColor DarkYellow
    New-Item -ItemType Directory -Force -Path $RuntimeRefDir | Out-Null
    Copy-Item $GoldenRef $RuntimeRef -Force
    
    $RuntimeHash = (Get-FileHash $RuntimeRef -Algorithm SHA256).Hash.ToUpper()
    if ($RuntimeHash -ne $ExpectedHash) {
        Write-Host "  FEHLER: Runtime Hash-Mismatch nach Kopie!" -ForegroundColor Red
        exit 1
    }
    Write-Host "  [OK] Runtime Voice Reference erstellt" -ForegroundColor Green
}
else {
    $RuntimeHash = (Get-FileHash $RuntimeRef -Algorithm SHA256).Hash.ToUpper()
    if ($RuntimeHash -ne $ExpectedHash) {
        Write-Host "  FEHLER: Runtime Voice Reference Hash-Mismatch!" -ForegroundColor Red
        exit 1
    }
    Write-Host "  [OK] Runtime Voice Reference vorhanden" -ForegroundColor Green
}

Write-Host ""

# ============================================================
# Long-Form Test ausfuehren
# ============================================================
Write-Host "Schritt 3/4: Long-Form Test ($Winner, max $MaxMinutes min)..." -ForegroundColor Yellow

$LongformScript = Join-Path $ProjectRoot "benchmark\phase4_longform.py"

if (-not (Test-Path $LongformScript)) {
    Write-Host "  FEHLER: $LongformScript nicht gefunden" -ForegroundColor Red
    exit 1
}

$LongformArgs = @("--winner", $Winner, "--max-minutes", $MaxMinutes)
if ($Quick) {
    $LongformArgs += "--quick"
}

Write-Host "  Starte Long-Form-Test..." -ForegroundColor Gray
Write-Host "  Parameter: winner=$Winner, max-minutes=$MaxMinutes, quick=$Quick" -ForegroundColor Gray
Write-Host ""

$LongformOutput = Join-Path $ResultsDir "longform_output.txt"
$StartTime = Get-Date

$env:VOICEOVER_ROOT = $ProjectRoot

Push-Location $ProjectRoot
try {
    & $PythonCmd $LongformScript @LongformArgs *> $LongformOutput
    $ExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

$EndTime = Get-Date
$TotalTime = ($EndTime - $StartTime).TotalMinutes

# Reports kopieren
$ReportMd = Join-Path $RepoRoot "PHASE4_LONGFORM_REPORT.md"
$ReportJson = Join-Path $RepoRoot "PHASE4_LONGFORM_REPORT.json"

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
    Write-Host ""
    
    # Audio-Dateien auflisten
    $OutputDir = Join-Path $ProjectRoot "output"
    $lfDirs = Get-ChildItem $OutputDir -Directory -Filter "phase4_longform_*" -ErrorAction SilentlyContinue | Sort-Object Name
    
    if ($lfDirs.Count -gt 0) {
        Write-Host "Audio-Dateien:" -ForegroundColor White
        foreach ($d in $lfDirs) {
            $wavs = Get-ChildItem $d.FullName -Filter "*.wav" -ErrorAction SilentlyContinue
            foreach ($w in $wavs) {
                $sizeMB = [math]::Round($w.Length / (1024*1024), 1)
                Write-Host "  $($w.FullName) ($sizeMB MB)" -ForegroundColor Gray
            }
        }
    }
    
    Write-Host ""
    Write-Host "Status:" -ForegroundColor Yellow
    Write-Host "  Repository Verified: OK" -ForegroundColor Green
    Write-Host "  Target Hardware Run: OK" -ForegroundColor Green
    Write-Host "  Long-Form Verified:  OK" -ForegroundColor Green
    Write-Host ""
    Write-Host "Results: $ResultsDir" -ForegroundColor Gray
}
else {
    Write-Host "LONG-FORM BENCHMARK FEHLGESCHLAGEN (Exit-Code: $ExitCode)" -ForegroundColor Red
    Write-Host "Output: $LongformOutput" -ForegroundColor Red
    Write-Host ""
    Write-Host "Letzte Zeilen:" -ForegroundColor Yellow
    Get-Content $LongformOutput -Tail 30
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan

exit $ExitCode
