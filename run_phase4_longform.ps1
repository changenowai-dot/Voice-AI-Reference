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
# DISCOVERY: Python, Modelle, Runtime Reference
# ============================================================
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "DISCOVERY: Lokale Ressourcen suchen..." -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""

# ------------------------------------------------------------
# Python-Discovery (gleiche Logik wie run_phase4_target.ps1)
# ------------------------------------------------------------
Write-Host "[1/3] Python-Discovery..." -ForegroundColor Cyan

$PythonCmd = $null
$PythonSource = ""

# Prioritaet A: Explizite Environment-Variable
if ($env:VOICEOVER_PYTHON) {
    if (Test-Path $env:VOICEOVER_PYTHON) {
        $PythonCmd = $env:VOICEOVER_PYTHON
        $PythonSource = "VOICEOVER_PYTHON (explicit)"
        Write-Host "  [OK] Explicit: $PythonCmd" -ForegroundColor Green
    }
}

# Prioritaet B: Repository .venv
if (-not $PythonCmd) {
    $RepoVenv = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path $RepoVenv) {
        $PythonCmd = $RepoVenv
        $PythonSource = "Repository .venv"
        Write-Host "  [OK] Repository: $PythonCmd" -ForegroundColor Green
    }
}

# Prioritaet C: Bekannte VoiceOverApp-Runtimes
if (-not $PythonCmd) {
    $SearchPatterns = @(
        "$env:USERPROFILE\Downloads\VoiceOverApp*",
        "$env:USERPROFILE\Documents\VoiceOverApp*",
        "$env:USERPROFILE\Desktop\VoiceOverApp*",
        (Join-Path (Split-Path $RepoRoot -Parent) "VoiceOverApp*")
    )
    
    foreach ($pattern in $SearchPatterns) {
        $candidates = Get-ChildItem -Path $pattern -Directory -ErrorAction SilentlyContinue | 
                      Where-Object { $_.FullName -ne $RepoRoot }
        foreach ($cand in $candidates) {
            $venvPy = Join-Path $cand.FullName ".venv\Scripts\python.exe"
            if (Test-Path $venvPy) {
                try {
                    $torchCheck = & $venvPy -c "import torch; print('OK' if torch.cuda.is_available() else 'NO_CUDA')" 2>&1
                    if ($torchCheck -eq "OK") {
                        $PythonCmd = $venvPy
                        $PythonSource = "External: $($cand.FullName)"
                        Write-Host "  [OK] External: $PythonCmd" -ForegroundColor Green
                        break
                    }
                } catch { }
            }
        }
        if ($PythonCmd) { break }
    }
}

# Prioritaet D: Systemweites Python
if (-not $PythonCmd) {
    $pythonCandidates = @("python", "python3", "py")
    foreach ($py in $pythonCandidates) {
        try {
            $ver = & $py --version 2>&1
            if ($LASTEXITCODE -eq 0 -and $ver -match "Python 3\.") {
                $PythonCmd = $py
                $PythonSource = "System Python"
                Write-Host "  [WARN] System Python: $ver" -ForegroundColor DarkYellow
                break
            }
        } catch { }
    }
}

if (-not $PythonCmd) {
    Write-Host "  [FAIL] Python nicht gefunden." -ForegroundColor Red
    exit 1
}

Write-Host "  Python: $PythonCmd ($PythonSource)" -ForegroundColor Green

# ------------------------------------------------------------
# Model-Root-Discovery (Multi-Root)
# ------------------------------------------------------------
Write-Host "[2/3] Model-Root-Discovery (Multi-Root)..." -ForegroundColor Cyan

$AllModelsRoots = @()

# Prioritaet A: Explizite Environment-Variablen
if ($env:VOICEOVER_MODELS_ROOTS) {
    foreach ($r in ($env:VOICEOVER_MODELS_ROOTS -split [IO.Path]::PathSeparator)) {
        $r = $r.Trim()
        if ($r -and (Test-Path $r)) { $AllModelsRoots += $r }
    }
}
if ($env:VOICEOVER_MODELS_DIR -and (Test-Path $env:VOICEOVER_MODELS_DIR)) {
    if ($env:VOICEOVER_MODELS_DIR -notin $AllModelsRoots) {
        $AllModelsRoots += $env:VOICEOVER_MODELS_DIR
    }
}

# Prioritaet B: Repository project\models
$RepoModels = Join-Path $ProjectRoot "models"
if ((Test-Path $RepoModels) -and ($RepoModels -notin $AllModelsRoots)) {
    $AllModelsRoots += $RepoModels
}

# Prioritaet C: Externe VoiceOverApp-Installationen
$SearchRoots = @("$env:USERPROFILE\Downloads", "$env:USERPROFILE\Documents", "$env:USERPROFILE\Desktop")
$ParentOfRepo = Split-Path $RepoRoot -Parent
if ($ParentOfRepo -and $ParentOfRepo -notin $SearchRoots) { $SearchRoots += $ParentOfRepo }

foreach ($searchDir in $SearchRoots) {
    if (-not (Test-Path $searchDir)) { continue }
    $candidates = Get-ChildItem -Path "$searchDir\VoiceOverApp*" -Directory -ErrorAction SilentlyContinue |
                  Where-Object { $_.FullName -ne $RepoRoot }
    foreach ($cand in $candidates) {
        $modelsDir = Join-Path $cand.FullName "models"
        if ((Test-Path $modelsDir) -and ($modelsDir -notin $AllModelsRoots)) {
            $AllModelsRoots += $modelsDir
            Write-Host "  [OK] External: $modelsDir" -ForegroundColor Green
        }
    }
}

$ModelsRoot = $null
if ($AllModelsRoots.Count -gt 0) { $ModelsRoot = $AllModelsRoots[0] }
else {
    $ModelsRoot = Join-Path $ProjectRoot "models"
    $AllModelsRoots += $ModelsRoot
}

Write-Host "  Primary Root: $ModelsRoot" -ForegroundColor Green
Write-Host "  Total Roots:  $($AllModelsRoots.Count)" -ForegroundColor Green

# ------------------------------------------------------------
# Runtime-Reference-Discovery
# ------------------------------------------------------------
Write-Host "[3/3] Runtime-Reference-Discovery..." -ForegroundColor Cyan

$ExpectedHash = "B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025"
$RuntimeRef = $null

if ($env:VOICEOVER_RUNTIME_REF -and (Test-Path $env:VOICEOVER_RUNTIME_REF)) {
    $RuntimeRef = $env:VOICEOVER_RUNTIME_REF
    Write-Host "  [OK] Explicit: $RuntimeRef" -ForegroundColor Green
}

if (-not $RuntimeRef) {
    $SearchPatterns = @(
        "$env:USERPROFILE\Downloads\VoiceOverApp*",
        "$env:USERPROFILE\Documents\VoiceOverApp*",
        (Join-Path (Split-Path $RepoRoot -Parent) "VoiceOverApp*")
    )
    foreach ($pattern in $SearchPatterns) {
        $candidates = Get-ChildItem -Path $pattern -Directory -ErrorAction SilentlyContinue | 
                      Where-Object { $_.FullName -ne $RepoRoot }
        foreach ($cand in $candidates) {
            $refPath = Join-Path $cand.FullName "cache\voice_refs\VD-E.wav"
            if (Test-Path $refPath) {
                $hash = (Get-FileHash $refPath -Algorithm SHA256).Hash.ToUpper()
                if ($hash -eq $ExpectedHash) {
                    $RuntimeRef = $refPath
                    Write-Host "  [OK] External: $RuntimeRef" -ForegroundColor Green
                    break
                }
            }
        }
        if ($RuntimeRef) { break }
    }
}

if ($RuntimeRef) {
    Write-Host "  Runtime Ref: $RuntimeRef" -ForegroundColor DarkGray
}

# Environment setzen
$env:VOICEOVER_ROOT = $ProjectRoot
$env:VOICEOVER_MODELS_DIR = $ModelsRoot
$env:VOICEOVER_MODELS_ROOTS = ($AllModelsRoots -join [IO.Path]::PathSeparator)
if ($RuntimeRef) {
    $env:VOICEOVER_RUNTIME_REF = $RuntimeRef
    $env:VOICEOVER_REFS_DIR = Split-Path $RuntimeRef -Parent
}

Write-Host ""

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
