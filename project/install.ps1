# ============================================================
#  VoiceOverApp - install.ps1
#  Checks and installs automatically:
#    - Python 3.10-3.13 (winget if missing)
#    - Virtual environment (.venv)
#    - PyTorch with CUDA 12.8 (RTX 50xx/Blackwell, cu128)
#      with CPU fallback
#    - Python packages (requirements.txt incl. qwen-tts)
#    - FFmpeg (winget or download to tools/)
#    - Qwen3-TTS models (Hugging Face, Apache-2.0)
#  Existing components are reused.
#  Free of charge, no API keys, no subscriptions.
#  ASCII-only source, PowerShell 5.1 compatible.
# ============================================================
param(
    [switch]$SkipModels,
    [switch]$CpuOnly
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root
New-Item -ItemType Directory -Force -Path "logs" | Out-Null
$InstallLog = Join-Path $Root "logs\install.log"

function Log([string]$msg, [string]$color = "Gray") {
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host $msg -ForegroundColor $color
    Add-Content -Path $InstallLog -Value "[$stamp] $msg" -Encoding UTF8
}

function Fail([string]$msg) {
    Log $msg "Red"
    Log "INSTALLATION = FAIL" "Red"
    if ($env:VOICEOVER_NONINTERACTIVE) { exit 1 }
    Read-Host "Enter to exit"
    exit 1
}

Log "=== VoiceOverApp Installation ===" "Cyan"

# ------------------------------------------------------------ 1) Python
function Find-Python {
    if (Test-Path -LiteralPath ".venv\Scripts\python.exe") { return ".venv\Scripts\python.exe" }
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        foreach ($v in @("3.12", "3.11", "3.13", "3.10")) {
            $out = & py -$v -c "import sys; print(sys.executable)" 2>$null
            if ($out -and -not ($out -like "*WindowsApps*")) { return "py -$v" }
        }
    }
    foreach ($name in @("python3.12", "python3.11", "python3.13", "python", "python3")) {
        $g = Get-Command $name -ErrorAction SilentlyContinue
        if ($g -and $g.Source -and -not ($g.Source -like "*WindowsApps*")) {
            return $name
        }
    }
    return $null
}

$Python = Find-Python
if (-not $Python) {
    Log "Python 3.10-3.13 not found - installing Python 3.12 via winget ..." "Yellow"
    try {
        winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements --silent | Out-Null
    } catch {
        Fail ("winget failed: {0}. Please install Python 3.12 from python.org and run again." -f $_)
    }
    $found = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python" -Filter python.exe -Recurse -ErrorAction SilentlyContinue |
             Where-Object { $_.DirectoryName -match "Python312|Python311|Python313" } | Select-Object -First 1
    if ($found) { $Python = $found.FullName }
    if (-not $Python) {
        Fail "Python was installed but is not on PATH. Please close this window and run START.bat again."
    }
}
Log "Python: $Python"

# ------------------------------------------------- 2) Virtual environment
if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    Log "Creating virtual environment .venv ..." "Yellow"
    if ($Python -like "py *") {
        $parts = $Python.Split(" ")
        & $parts[0] $parts[1] -m venv .venv
    } else {
        & $Python -m venv .venv
    }
    if ($LASTEXITCODE -ne 0) { Fail "venv creation returned non-zero exit code." }
}

$Vpy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Vpy)) {
    Fail ".venv\Scripts\python.exe not found after venv creation."
}
Log "Virtual environment python: $Vpy" "Green"

# Quick self-test of venv python
& $Vpy --version 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { Fail ".venv python.exe --version failed." }

# Self-test of pip BEFORE any install
& $Vpy -m pip --version 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { Fail "python -m pip is not working in .venv (ensure pip is bundled with Python)." }

# pip upgrade (best-effort)
Log "Upgrading pip ..."
& $Vpy -m pip install --upgrade pip --quiet
if ($LASTEXITCODE -ne 0) {
    Log "pip upgrade returned non-zero (continuing with existing pip)." "Yellow"
}

# ------------------------------------------------------- 3) PyTorch/CUDA
$needTorch = $true
$hasTorch = & $Vpy -c "import torch; print(torch.__version__)" 2>$null
if ($LASTEXITCODE -eq 0 -and $hasTorch) {
    $needTorch = $false
    Log "PyTorch already installed: $hasTorch" "Green"
}

function Has-NvidiaGPU {
    try { nvidia-smi *> $null; return ($LASTEXITCODE -eq 0) }
    catch { return $false }
    return $false
}

if ($needTorch) {
    $gpu = (-not $CpuOnly) -and (Has-NvidiaGPU)
    if ($gpu) {
        Log "Installing PyTorch with CUDA 12.8 (cu128) - download ~3 GB, one-time ..." "Yellow"
        & $Vpy -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128 --quiet
        if ($LASTEXITCODE -ne 0) {
            Log "CUDA install failed - falling back to CPU-only PyTorch." "Yellow"
            & $Vpy -m pip install torch torchaudio --quiet
            if ($LASTEXITCODE -ne 0) { Fail "CPU PyTorch install also failed." }
        }
    } else {
        Log "No NVIDIA GPU detected (or -CpuOnly) - installing CPU PyTorch ..." "Yellow"
        & $Vpy -m pip install torch torchaudio --quiet
        if ($LASTEXITCODE -ne 0) { Fail "CPU PyTorch install failed." }
    }
}
$t = & $Vpy -c "import torch; print(torch.__version__, torch.version.cuda)" 2>$null
if ($LASTEXITCODE -ne 0 -or -not $t) { Fail "PyTorch import failed after install." }
Log "PyTorch active: $t" "Green"

# --------------------------------------------------- 4) Packages (app)
Log "Installing Python packages (qwen-tts, transformers, ...) ..." "Yellow"
& $Vpy -m pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) {
    Log "First requirements install failed; retrying with verbose output ..." "Yellow"
    & $Vpy -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { Fail "Package installation failed - see messages above." }
}
Log "Requirements installed." "Green"

# ------------------------------------------------------------ 5) FFmpeg
$ff = Get-Command ffmpeg -ErrorAction SilentlyContinue
$ffLocal = Test-Path -LiteralPath "tools\ffmpeg\ffmpeg.exe"
if (-not $ff -and -not $ffLocal) {
    Log "FFmpeg missing - trying winget ..." "Yellow"
    try {
        winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements --silent | Out-Null
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    } catch { Log ("winget ffmpeg failed: {0}" -f $_) "Yellow" }
    $ff = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if (-not $ff) {
        Log "Downloading FFmpeg to tools\ffmpeg ..." "Yellow"
        try {
            New-Item -ItemType Directory -Force -Path "tools" | Out-Null
            $zip = Join-Path $env:TEMP "ffmpeg.zip"
            Invoke-WebRequest -Uri "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile $zip -UseBasicParsing
            Expand-Archive -Path $zip -DestinationPath "tools\_ff" -Force
            $exe = Get-ChildItem "tools\_ff" -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
            New-Item -ItemType Directory -Force -Path "tools\ffmpeg" | Out-Null
            if ($exe) {
                Move-Item $exe.FullName "tools\ffmpeg\ffmpeg.exe" -Force
            }
            Remove-Item "tools\_ff" -Recurse -Force -ErrorAction SilentlyContinue
            Remove-Item $zip -Force -ErrorAction SilentlyContinue
        } catch {
            Log ("FFmpeg download failed: {0}. MP3 output disabled (WAV works)." -f $_) "Yellow"
        }
    }
}

# ------------------------------------------------------ 6) Models
if (-not $SkipModels) {
    Log "Downloading Qwen3-TTS models (1.7B CustomVoice + Tokenizer, ~4 GB) ..." "Yellow"
    Log "(Progress shown in console; cancel with Ctrl+C, resumes on next run)"
    & $Vpy app\main.py --download-models
    if ($LASTEXITCODE -ne 0) {
        Log "Model download failed - check Internet connection and run again." "Red"
        Log "(You can re-run later with: SETUP.ps1; models are downloaded incrementally.)" "Yellow"
    } else {
        Log "Models ready." "Green"
    }
}

# ------------------------------------------------ 7) Final checks + markers
Log "Writing versions.json + environment.json ..."
& $Vpy -c "import json,torch,transformers,platform;d={'created':__import__('datetime').datetime.now().isoformat(),'python':platform.python_version(),'torch':torch.__version__,'torch_cuda':torch.version.cuda,'transformers':transformers.__version__,'app':'1.0.0'};json.dump(d,open('versions.json','w'),indent=2)"
if ($LASTEXITCODE -ne 0) { Fail "Could not write versions.json - Python environment not usable." }

New-Item -ItemType File -Path ".installed" -Force | Out-Null
Log "=== Installation complete ===" "Green"
Log "INSTALLATION = PASS" "Green"
Log "Start: double-click START.bat"
if (-not $env:VOICEOVER_NONINTERACTIVE) {
    Read-Host "Enter to exit"
}
exit 0
