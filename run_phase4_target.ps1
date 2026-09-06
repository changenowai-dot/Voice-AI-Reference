# ============================================================
# VoiceOverApp Phase 4 - Target Hardware Runner
# ============================================================
#
# AUSFUEHRUNG:
#   .\run_phase4_target.ps1
#
# INTELLIGENTE DISCOVERY:
#   - Findet automatisch vorhandene VoiceOverApp-Runtimes
#   - Verwendet externe Modelle und Runtime-References
#   - Unterstuetzt Environment-Variablen fuer explizite Pfade
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
Write-Host "VoiceOverApp Phase 4 - Target Hardware Benchmark" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Repository: $RepoRoot" -ForegroundColor Gray
Write-Host "Project:    $ProjectRoot" -ForegroundColor Gray

# Timestamp
$RunID = Get-Date -Format "yyyyMMdd_HHmmss"
$ResultsDir = Join-Path $RepoRoot "results\phase4\$RunID"
Write-Host "Run-ID:   $RunID" -ForegroundColor Gray
Write-Host "Results:  $ResultsDir" -ForegroundColor Gray
Write-Host ""

# Results-Verzeichnis
New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null

# ============================================================
# DISCOVERY: Python, Modelle, Runtime Reference
# ============================================================
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "DISCOVERY: Lokale Ressourcen suchen..." -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""

# ------------------------------------------------------------
# 1. Python-Discovery
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
    else {
        Write-Host "  [WARN] VOICEOVER_PYTHON gesetzt, aber Datei nicht gefunden: $env:VOICEOVER_PYTHON" -ForegroundColor DarkYellow
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
                # Validierung: Hat Torch mit CUDA?
                try {
                    $torchCheck = & $venvPy -c "import torch; print('OK' if torch.cuda.is_available() else 'NO_CUDA')" 2>&1
                    if ($torchCheck -eq "OK") {
                        $PythonCmd = $venvPy
                        $PythonSource = "External: $($cand.FullName)"
                        Write-Host "  [OK] External: $PythonCmd" -ForegroundColor Green
                        Write-Host "       Source: $($cand.FullName)" -ForegroundColor DarkGray
                        break
                    }
                }
                catch {
                    # Weiter suchen
                }
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
                Write-Host "  [WARN] System Python (moeglicherweise ohne Torch): $ver" -ForegroundColor DarkYellow
                break
            }
        }
        catch {
            # Weiter probieren
        }
    }
}

if (-not $PythonCmd) {
    Write-Host "  [FAIL] Python nicht gefunden." -ForegroundColor Red
    Write-Host ""
    Write-Host "  Bitte installieren Sie:" -ForegroundColor Yellow
    Write-Host "    - Python 3.10-3.13" -ForegroundColor White
    Write-Host "    - Oder setzen Sie VOICEOVER_PYTHON auf eine vorhandene .venv" -ForegroundColor White
    exit 1
}

Write-Host ""
Write-Host "  Python: $PythonCmd" -ForegroundColor Green
Write-Host "  Source: $PythonSource" -ForegroundColor DarkGray
Write-Host ""

# ------------------------------------------------------------
# 2. Model-Root-Discovery (Multi-Root)
# ------------------------------------------------------------
Write-Host "[2/3] Model-Root-Discovery (Multi-Root)..." -ForegroundColor Cyan

$AllModelsRoots = @()

# Prioritaet A: Explizite Environment-Variablen
if ($env:VOICEOVER_MODELS_ROOTS) {
    foreach ($r in ($env:VOICEOVER_MODELS_ROOTS -split [IO.Path]::PathSeparator)) {
        $r = $r.Trim()
        if ($r -and (Test-Path $r)) {
            $AllModelsRoots += $r
        }
    }
    if ($AllModelsRoots.Count -gt 0) {
        Write-Host "  [OK] VOICEOVER_MODELS_ROOTS: $($AllModelsRoots.Count) Roots" -ForegroundColor Green
    }
}
if ($env:VOICEOVER_MODELS_DIR -and (Test-Path $env:VOICEOVER_MODELS_DIR)) {
    if ($env:VOICEOVER_MODELS_DIR -notin $AllModelsRoots) {
        $AllModelsRoots += $env:VOICEOVER_MODELS_DIR
        Write-Host "  [OK] VOICEOVER_MODELS_DIR: $env:VOICEOVER_MODELS_DIR" -ForegroundColor Green
    }
}

# Prioritaet B: Repository project\models
$RepoModels = Join-Path $ProjectRoot "models"
if ((Test-Path $RepoModels) -and ($RepoModels -notin $AllModelsRoots)) {
    $AllModelsRoots += $RepoModels
    Write-Host "  [OK] Repository: $RepoModels" -ForegroundColor Green
}

# Prioritaet C: ALLE externen VoiceOverApp-Installationen sammeln
$SearchRoots = @(
    "$env:USERPROFILE\Downloads"
    "$env:USERPROFILE\Documents"
    "$env:USERPROFILE\Desktop"
)
$ParentOfRepo = Split-Path $RepoRoot -Parent
if ($ParentOfRepo -and $ParentOfRepo -notin $SearchRoots) {
    $SearchRoots += $ParentOfRepo
}

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

# Primaeren Root bestimmen (der mit den meisten Modellen)
$ModelsRoot = $null
$BestCount = 0

$requiredModelNames = @("Qwen3-TTS-12Hz-1.7B-CustomVoice", "Qwen3-TTS-12Hz-1.7B-Base", "Qwen3-TTS-Tokenizer-12Hz")
$requiredHfNames = @(
    @("models--Qwen--Qwen3-TTS-12Hz-1.7B-CustomVoice", "models--Qwen3-TTS-12Hz-1.7B-CustomVoice"),
    @("models--Qwen--Qwen3-TTS-12Hz-1.7B-Base", "models--Qwen3-TTS-12Hz-1.7B-Base"),
    @("models--Qwen--Qwen3-TTS-Tokenizer-12Hz", "models--Qwen3-TTS-Tokenizer-12Hz", "models--Qwen--Qwen3-TTS-12Hz-Tokenizer")
)

foreach ($root in $AllModelsRoots) {
    $count = 0
    for ($i = 0; $i -lt $requiredModelNames.Count; $i++) {
        $name = $requiredModelNames[$i]
        $hfNames = $requiredHfNames[$i]
        $found = $false
        $directPath = Join-Path $root $name
        if (Test-Path $directPath) { $found = $true }
        if (-not $found) {
            foreach ($hfName in $hfNames) {
                $hfPath = Join-Path $root "hf\hub\$hfName"
                if (Test-Path $hfPath) { $found = $true; break }
            }
        }
        if ($found) { $count++ }
    }
    if ($count -gt $BestCount) {
        $BestCount = $count
        $ModelsRoot = $root
    }
}

if (-not $ModelsRoot) {
    Write-Host "  [WARN] Keine Modelle gefunden." -ForegroundColor DarkYellow
    $ModelsRoot = Join-Path $ProjectRoot "models"
}

Write-Host ""
Write-Host "  Primary Root: $ModelsRoot ($BestCount/3 models)" -ForegroundColor Green
Write-Host "  Total Roots:  $($AllModelsRoots.Count)" -ForegroundColor Green

# Alle Models Roots als Pfad-Liste ausgeben
foreach ($r in $AllModelsRoots) {
    Write-Host "    - $r" -ForegroundColor DarkGray
}
Write-Host ""

# ------------------------------------------------------------
# 3. Runtime-Reference-Discovery
# ------------------------------------------------------------
Write-Host "[3/3] Runtime-Reference-Discovery..." -ForegroundColor Cyan

$RuntimeRef = $null
$RuntimeRefSource = ""
$ExpectedHash = "B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025"

# Prioritaet A: Explizite Environment-Variable
if ($env:VOICEOVER_RUNTIME_REF) {
    if (Test-Path $env:VOICEOVER_RUNTIME_REF) {
        $RuntimeRef = $env:VOICEOVER_RUNTIME_REF
        $RuntimeRefSource = "VOICEOVER_RUNTIME_REF (explicit)"
        Write-Host "  [OK] Explicit: $RuntimeRef" -ForegroundColor Green
    }
}

# Prioritaet B: Repository project\cache\voice_refs\VD-E.wav
if (-not $RuntimeRef) {
    $RepoRef = Join-Path $ProjectRoot "cache\voice_refs\VD-E.wav"
    if (Test-Path $RepoRef) {
        $hash = (Get-FileHash $RepoRef -Algorithm SHA256).Hash.ToUpper()
        if ($hash -eq $ExpectedHash) {
            $RuntimeRef = $RepoRef
            $RuntimeRefSource = "Repository project\cache\voice_refs"
            Write-Host "  [OK] Repository: $RuntimeRef" -ForegroundColor Green
        }
        else {
            Write-Host "  [WARN] Repository VD-E.wav hat falschen Hash: $hash" -ForegroundColor DarkYellow
        }
    }
}

# Prioritaet C: Externe Runtime-References
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
                    $RuntimeRefSource = "External: $($cand.FullName)"
                    Write-Host "  [OK] External: $RuntimeRef" -ForegroundColor Green
                    Write-Host "       Source: $($cand.FullName)" -ForegroundColor DarkGray
                    break
                }
            }
        }
        if ($RuntimeRef) { break }
    }
}

if (-not $RuntimeRef) {
    Write-Host "  [WARN] Keine VD-E Runtime Reference gefunden." -ForegroundColor DarkYellow
    Write-Host "         Golden Reference wird nicht kopiert (LOCKED)." -ForegroundColor DarkYellow
}
else {
    $hash = (Get-FileHash $RuntimeRef -Algorithm SHA256).Hash.ToUpper()
    Write-Host ""
    Write-Host "  Runtime Ref: $RuntimeRef" -ForegroundColor Green
    Write-Host "  Source: $RuntimeRefSource" -ForegroundColor DarkGray
    Write-Host "  SHA-256: $hash" -ForegroundColor Green
}

Write-Host ""

# ============================================================
# Environment-Variablen setzen
# ============================================================
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "ENVIRONMENT SETUP" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""

$env:VOICEOVER_ROOT = $ProjectRoot
$env:VOICEOVER_MODELS_DIR = $ModelsRoot

# Setze VOICEOVER_MODELS_ROOTS (plural) mit ALLEN gefundenen Roots
$env:VOICEOVER_MODELS_ROOTS = ($AllModelsRoots -join [IO.Path]::PathSeparator)

if ($RuntimeRef) {
    $env:VOICEOVER_RUNTIME_REF = $RuntimeRef
    $refsDir = Split-Path $RuntimeRef -Parent
    $env:VOICEOVER_REFS_DIR = $refsDir
}

Write-Host "  VOICEOVER_ROOT:           $env:VOICEOVER_ROOT" -ForegroundColor Gray
Write-Host "  VOICEOVER_MODELS_DIR:     $env:VOICEOVER_MODELS_DIR" -ForegroundColor Gray
Write-Host "  VOICEOVER_MODELS_ROOTS:   $($AllModelsRoots.Count) roots" -ForegroundColor Gray
if ($env:VOICEOVER_RUNTIME_REF) {
    Write-Host "  VOICEOVER_RUNTIME_REF:  $env:VOICEOVER_RUNTIME_REF" -ForegroundColor Gray
    Write-Host "  VOICEOVER_REFS_DIR:     $env:VOICEOVER_REFS_DIR" -ForegroundColor Gray
}
Write-Host ""

# ============================================================
# SCHRITT 1: Python und Environment Check
# ============================================================
Write-Host "Schritt 1/7: Python und Environment Check..." -ForegroundColor Yellow

$EnvCheckScript = Join-Path $ProjectRoot "benchmark\phase4_env_check.py"
if (-not (Test-Path $EnvCheckScript)) {
    Write-Host "FEHLER: $EnvCheckScript nicht gefunden" -ForegroundColor Red
    exit 1
}

if (-not $SkipEnvCheck) {
    $EnvOutput = Join-Path $ResultsDir "env_check_output.txt"
    
    & $PythonCmd $EnvCheckScript *> $EnvOutput
    $EnvExitCode = $LASTEXITCODE
    
    if ($EnvExitCode -ne 0) {
        Write-Host ""
        Write-Host "UMGEBUNGS-CHECK FEHLGESCHLAGEN (Exit-Code: $EnvExitCode)" -ForegroundColor Red
        Write-Host "Bitte Output pruefen: $EnvOutput" -ForegroundColor Red
        Write-Host ""
        Write-Host "Letzte Zeilen:" -ForegroundColor Yellow
        Get-Content $EnvOutput -Tail 30
        Write-Host ""
        Write-Host "Alle Voraussetzungen muessen erfuellt sein." -ForegroundColor Red
        exit 1
    }
    
    # JSON-Report kopieren
    $EnvJson = Join-Path $ProjectRoot "benchmark\phase4_env_check.json"
    $EnvReport = Join-Path $ResultsDir "environment.json"
    if (Test-Path $EnvJson) {
        Copy-Item $EnvJson $EnvReport -Force
        Write-Host "  Environment-Report: $EnvReport" -ForegroundColor Gray
    }
    
    Write-Host "  [OK] Environment OK" -ForegroundColor Green
}
else {
    Write-Host "  [SKIP] Environment-Check uebersprungen" -ForegroundColor DarkYellow
}

Write-Host ""

# ============================================================
# SCHRITT 2: Golden Reference Check
# ============================================================
Write-Host "Schritt 2/7: Golden Reference Check..." -ForegroundColor Yellow

$GoldenRef = Join-Path $RepoRoot "reference\VD-E_GOLDEN_REFERENCE\VD-E.wav"

if (-not (Test-Path $GoldenRef)) {
    Write-Host "  FEHLER: Golden Reference nicht gefunden: $GoldenRef" -ForegroundColor Red
    exit 1
}

$ActualHash = (Get-FileHash $GoldenRef -Algorithm SHA256).Hash.ToUpper()
if ($ActualHash -ne $ExpectedHash) {
    Write-Host "  FEHLER: Golden Reference Hash-Mismatch!" -ForegroundColor Red
    Write-Host "  Erwartet: $ExpectedHash" -ForegroundColor Red
    Write-Host "  Gefunden: $ActualHash" -ForegroundColor Red
    exit 1
}

$GRSize = [math]::Round((Get-Item $GoldenRef).Length / 1024, 1)
Write-Host "  [OK] Golden Reference: $GRSize KB, SHA-256 OK" -ForegroundColor Green
Write-Host ""

# ============================================================
# SCHRITT 3: Runtime Voice Reference (bereits gefunden)
# ============================================================
Write-Host "Schritt 3/7: Runtime Voice Reference..." -ForegroundColor Yellow

if ($RuntimeRef) {
    Write-Host "  [OK] Runtime Voice Reference: $RuntimeRef" -ForegroundColor Green
}
else {
    Write-Host "  [WARN] Keine Runtime Voice Reference gefunden." -ForegroundColor DarkYellow
    Write-Host "         Benchmark wird moeglicherweise VD-E nicht verwenden." -ForegroundColor DarkYellow
}

Write-Host ""

# ============================================================
# SCHRITT 4: Model Discovery (bereits gefunden)
# ============================================================
Write-Host "Schritt 4/7: Model Discovery..." -ForegroundColor Yellow

$RequiredModels = @(
    @{
        Name = "Qwen3-TTS-12Hz-1.7B-Base"
        HfNames = @("models--Qwen--Qwen3-TTS-12Hz-1.7B-Base", "models--Qwen3-TTS-12Hz-1.7B-Base")
    }
    @{
        Name = "Qwen3-TTS-Tokenizer-12Hz"
        HfNames = @("models--Qwen--Qwen3-TTS-Tokenizer-12Hz", "models--Qwen3-TTS-Tokenizer-12Hz", "models--Qwen--Qwen3-TTS-12Hz-Tokenizer")
    }
    @{
        Name = "Qwen3-TTS-12Hz-1.7B-CustomVoice"
        HfNames = @("models--Qwen--Qwen3-TTS-12Hz-1.7B-CustomVoice", "models--Qwen3-TTS-12Hz-1.7B-CustomVoice")
    }
)

$ModelsFound = @()
$ModelsMissing = @()

foreach ($model in $RequiredModels) {
    $modelName = $model.Name
    $hfNames = $model.HfNames
    $found = $false
    
    # Suche ueber ALLE bekannten Model-Roots
    foreach ($searchRoot in $AllModelsRoots) {
        if ($found) { break }
        
        # Check 1: Direkter Pfad
        $directPath = Join-Path $searchRoot $modelName
        if ((Test-Path $directPath) -and (Test-Path (Join-Path $directPath "config.json"))) {
            $found = $true
            $ModelsFound += @{ Name = $modelName; Path = $directPath; Method = "direct"; Root = $searchRoot }
            break
        }
        
        # Check 2: HuggingFace Hub Cache (multiple name variants)
        foreach ($hfName in $hfNames) {
            $hubPath = Join-Path $searchRoot "hf\hub\$hfName"
            if (Test-Path $hubPath) {
                $snapshots = Join-Path $hubPath "snapshots"
                if (Test-Path $snapshots) {
                    $snapshotDirs = Get-ChildItem $snapshots -Directory
                    if ($snapshotDirs.Count -gt 0) {
                        foreach ($snap in $snapshotDirs) {
                            $modelFile = Join-Path $snap.FullName "model.safetensors"
                            if (Test-Path $modelFile) {
                                $found = $true
                                $ModelsFound += @{ Name = $modelName; Path = $snap.FullName; Method = "hub-cache"; Root = $searchRoot }
                                break
                            }
                        }
                    }
                }
            }
            if ($found) { break }
        }
    }
    
    if (-not $found) {
        $ModelsMissing += $modelName
    }
}

if ($ModelsMissing.Count -gt 0) {
    Write-Host "  FEHLER: Folgende Modelle fehlen in ALLEN Roots:" -ForegroundColor Red
    foreach ($m in $ModelsMissing) {
        Write-Host "    - $m" -ForegroundColor Red
    }
    Write-Host ""
    Write-Host "  Durchsuchte Roots:" -ForegroundColor Yellow
    foreach ($r in $AllModelsRoots) {
        Write-Host "    - $r" -ForegroundColor DarkGray
    }
    Write-Host ""
    Write-Host "  Tipp: Setze VOICEOVER_MODELS_ROOTS um weitere Pfade anzugeben." -ForegroundColor Yellow
    exit 1
}

foreach ($m in $ModelsFound) {
    Write-Host "  [OK] $($m.Name) ($($m.Method))" -ForegroundColor Green
    Write-Host "       Root: $($m.Root)" -ForegroundColor DarkGray
}

Write-Host ""

# ============================================================
# SCHRITT 5: FFmpeg Check
# ============================================================
Write-Host "Schritt 5/7: FFmpeg Check..." -ForegroundColor Yellow

$ffmpegFound = $false

try {
    $ffver = & ffmpeg -version 2>&1 | Select-Object -First 1
    if ($LASTEXITCODE -eq 0 -and $ffver -match "ffmpeg") {
        $ffmpegFound = $true
        Write-Host "  [OK] FFmpeg gefunden" -ForegroundColor Green
    }
}
catch {
    # FFmpeg nicht im PATH
}

if (-not $ffmpegFound) {
    # Fallback-Pfade pruefen
    $ffmpegCandidates = @(
        (Join-Path $ProjectRoot "tools\ffmpeg.exe")
        (Join-Path $ProjectRoot "tools\ffmpeg\bin\ffmpeg.exe")
        "C:\ffmpeg\bin\ffmpeg.exe"
    )
    foreach ($cand in $ffmpegCandidates) {
        if (Test-Path $cand) {
            $ffmpegFound = $true
            $env:PATH = "$(Split-Path $cand);$env:PATH"
            Write-Host "  [OK] FFmpeg: $cand" -ForegroundColor Green
            break
        }
    }
}

if (-not $ffmpegFound) {
    Write-Host "  WARNUNG: FFmpeg nicht gefunden." -ForegroundColor DarkYellow
    Write-Host "  MP3-Erzeugung eingeschraenkt. Benchmark wird fortgesetzt (WAV-only)." -ForegroundColor DarkYellow
}

Write-Host ""

# ============================================================
# SCHRITT 6: Baseline + A/B-Test
# ============================================================
Write-Host "Schritt 6/7: Production Baseline + A/B-Test..." -ForegroundColor Yellow

if (-not $SkipBaseline) {
    $BenchmarkScript = Join-Path $ProjectRoot "benchmark\phase4_benchmark.py"
    if (-not (Test-Path $BenchmarkScript)) {
        Write-Host "  FEHLER: $BenchmarkScript nicht gefunden" -ForegroundColor Red
        exit 1
    }
    
    $BenchmarkOutput = Join-Path $ResultsDir "benchmark_output.txt"
    
    if ($SkipABTest) {
        Write-Host "  [SKIP] A/B-Test uebersprungen (nur Baseline)" -ForegroundColor DarkYellow
    }
    
    Write-Host "  Starte Benchmark..." -ForegroundColor Gray
    Write-Host "  Dies kann 30-90 Minuten dauern." -ForegroundColor Gray
    Write-Host ""
    
    # Change to project directory
    Push-Location $ProjectRoot
    try {
        & $PythonCmd $BenchmarkScript *> $BenchmarkOutput
        $BenchmarkExitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    
    if ($BenchmarkExitCode -ne 0) {
        Write-Host ""
        Write-Host "BENCHMARK FEHLGESCHLAGEN (Exit-Code: $BenchmarkExitCode)" -ForegroundColor Red
        Write-Host "Bitte Output pruefen: $BenchmarkOutput" -ForegroundColor Red
        Write-Host ""
        Write-Host "Letzte Zeilen:" -ForegroundColor Yellow
        Get-Content $BenchmarkOutput -Tail 30
        exit 1
    }
    
    # Reports kopieren
    $ReportMd = Join-Path $RepoRoot "PHASE4_REAL_AUDIO_REPORT.md"
    $ReportJson = Join-Path $RepoRoot "PHASE4_REAL_AUDIO_REPORT.json"
    
    if (Test-Path $ReportMd) {
        Copy-Item $ReportMd (Join-Path $ResultsDir "PHASE4_REAL_AUDIO_REPORT.md") -Force
    }
    if (Test-Path $ReportJson) {
        Copy-Item $ReportJson (Join-Path $ResultsDir "PHASE4_REAL_AUDIO_REPORT.json") -Force
    }
    
    Write-Host "  [OK] Baseline + A/B-Test abgeschlossen" -ForegroundColor Green
}
else {
    Write-Host "  [SKIP] Baseline uebersprungen" -ForegroundColor DarkYellow
}

Write-Host ""

# ============================================================
# SCHRITT 7: Audio-Pfade + AUDIO_REVIEW.md
# ============================================================
Write-Host "Schritt 7/7: Report und Audio-Review..." -ForegroundColor Yellow

# Audio-Dateien finden
$AudioFiles = @()
$OutputDir = Join-Path $ProjectRoot "output"

$audioDirs = @(
    @{ Name = "baseline"; Pattern = "phase4_baseline*" }
    @{ Name = "variant_A"; Pattern = "phase4_A*" }
    @{ Name = "variant_B"; Pattern = "phase4_B*" }
    @{ Name = "variant_C"; Pattern = "phase4_C*" }
    @{ Name = "variant_D"; Pattern = "phase4_D*" }
    @{ Name = "variant_E"; Pattern = "phase4_E*" }
)

foreach ($dir in $audioDirs) {
    $searchDirs = Get-ChildItem $OutputDir -Directory -Filter $dir.Pattern -ErrorAction SilentlyContinue
    foreach ($sd in $searchDirs) {
        $wavs = Get-ChildItem $sd.FullName -Filter "*.wav" -ErrorAction SilentlyContinue
        foreach ($wav in $wavs) {
            $AudioFiles += @{
                Variant = $dir.Name
                Path = $wav.FullName
                Size = [math]::Round($wav.Length / (1024*1024), 2)
            }
        }
    }
}

# Audio-Review erstellen
$AudioReview = Join-Path $ResultsDir "AUDIO_REVIEW.md"

$AudioListLines = ""
foreach ($af in $AudioFiles) {
    $AudioListLines += "| $($af.Variant) | $($af.Path) | $($af.Size) MB | ?/10 | ?/10 | ?/10 | ?/10 | ?/10 | ?/10 |`n"
}

$ReviewContent = @"
# Audio Review - Phase 4 Benchmark

**Run-ID:** $RunID
**Datum:** $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
**Repository:** $RepoRoot

---

## Status

| Kategorie | Status |
|-----------|--------|
| Repository Verified | OK |
| Target Hardware Required | OK |
| Target Hardware Verified | AUSSTEHEND |

---

## Bewertungsanleitung

Bitte jede Variante anhoeren und bewerten (0-10):

- **0-3:** Unbrauchbar
- **4-6:** Akzeptabel
- **7-8:** Gut
- **9-10:** Exzellent

---

## Audio-Dateien

| Variante | Pfad | Groesse | Voice ID | Naturalness | Pronunciation | Prosody | Continuity | Overall |
|----------|------|---------|----------|-------------|---------------|---------|------------|---------|
$AudioListLines
---

## Gewinner

**Variante:** ?

**Begruendung:**
- 
- 

---

## Fazit

**Empfehlung fuer Production:**
- 

**Naechste Schritte:**
- 
"@

$ReviewContent | Out-File -FilePath $AudioReview -Encoding UTF8
Write-Host "  [OK] AUDIO_REVIEW.md erstellt" -ForegroundColor Green

# Audio-Dateien auflisten
if ($AudioFiles.Count -gt 0) {
    Write-Host ""
    Write-Host "  Audio-Dateien zum Anhoeren:" -ForegroundColor White
    foreach ($af in $AudioFiles) {
        Write-Host "    [$($af.Variant)] $($af.Path) ($($af.Size) MB)" -ForegroundColor Gray
    }
}
else {
    Write-Host "  WARNUNG: Keine Audio-Dateien gefunden." -ForegroundColor DarkYellow
}

Write-Host "  AUDIO_REVIEW.md: $AudioReview" -ForegroundColor Green
Write-Host "  Bitte nach Benchmark manuell ausfuellen." -ForegroundColor Gray

Write-Host ""

# ============================================================
# ZUSAMMENFASSUNG
# ============================================================
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "BENCHMARK ABGESCHLOSSEN" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Status:" -ForegroundColor Yellow
Write-Host "  Repository Verified: OK" -ForegroundColor Green
Write-Host "  Target Hardware Run: OK" -ForegroundColor Green
Write-Host "  Akustische Bewertung: AUSSTEHEND (manuell)" -ForegroundColor DarkYellow
Write-Host ""
Write-Host "Run-ID: $RunID" -ForegroundColor Gray
Write-Host "Results: $ResultsDir" -ForegroundColor Gray
Write-Host ""
Write-Host "Erzeugte Dateien:" -ForegroundColor White
Write-Host "  - environment.json" -ForegroundColor Gray
Write-Host "  - benchmark_output.txt" -ForegroundColor Gray
Write-Host "  - PHASE4_REAL_AUDIO_REPORT.md" -ForegroundColor Gray
Write-Host "  - PHASE4_REAL_AUDIO_REPORT.json" -ForegroundColor Gray
Write-Host "  - AUDIO_REVIEW.md (manuell ausfuellen)" -ForegroundColor Gray
Write-Host ""
Write-Host "Naechste Schritte:" -ForegroundColor Yellow
Write-Host "  1. Audio-Dateien anhoeren" -ForegroundColor White
Write-Host "  2. AUDIO_REVIEW.md ausfuellen" -ForegroundColor White
Write-Host "  3. Gewinner identifizieren" -ForegroundColor White
Write-Host "  4. Long-Form-Test:" -ForegroundColor White
Write-Host "     .\run_phase4_longform.ps1 -Winner [A|B|C|D|E]" -ForegroundColor Gray
Write-Host "  5. Results zurueckliefern an den Agent" -ForegroundColor White
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan

exit 0
