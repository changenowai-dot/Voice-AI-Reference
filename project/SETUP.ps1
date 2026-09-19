# ============================================================
#  VoiceOverApp -- SETUP.ps1 (one-time setup / preflight)
#
#  Checks and (if necessary) installs:
#    - Python 3.10-3.13
#    - Virtual environment .venv
#    - PyTorch (CUDA 12.8 Blackwell/RTX 50xx) or CPU fallback
#    - Python packages (requirements.txt, qwen-tts)
#    - FFmpeg
#    - Qwen3-TTS models (1.7B Base / CustomVoice / VoiceDesign)
#    - Voice reference WAVs (frozen-backup read-only import + verify)
#
#  ASCII-ONLY source. No Unicode literals. PowerShell 5.1 compatible.
#  After this script: run START.bat / START.ps1 / desktop.py
# ============================================================
param(
  [switch]$CpuOnly,
  [switch]$SkipModels
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
try { chcp 65001 | Out-Null } catch {}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root
Write-Host "== VoiceOverApp SETUP -- Preflight ==" -ForegroundColor Cyan
Write-Host "Root: $Root" -ForegroundColor Gray

# --- 1) Python discovery ---
function Find-Python {
  if (Test-Path -LiteralPath ".venv\Scripts\python.exe") { return ".venv\Scripts\python.exe" }
  $cands = @("py -3.12", "py -3.11", "python3.12", "python3", "python")
  foreach ($c in $cands) {
    try {
      $parts = $c.Split(" ")
      $exe = $parts[0]
      $arg = $null
      if ($parts.Count -gt 1) { $arg = $parts[1] }
      if ($arg) {
        $out = & $exe $arg -c "import sys; print(sys.executable)" 2>$null
      } else {
        $out = & $exe -c "import sys; print(sys.executable)" 2>$null
      }
      if ($out -and -not ($out -like "*WindowsApps*")) { return $c }
    } catch {}
  }
  return $null
}
$py = Find-Python
if (-not $py) {
  Write-Host "No Python 3.10-3.13 found -- install.ps1 will fetch it via winget." -ForegroundColor Yellow
}

# --- 2) Delegate to install.ps1 (venv, deps, CUDA, models; logs to logs/install.log) ---
$install = Join-Path $Root "install.ps1"
if (-not (Test-Path -LiteralPath $install)) {
  Write-Host "install.ps1 is missing!" -ForegroundColor Red
  exit 1
}
Write-Host "Running install.ps1 (Python, .venv, deps, CUDA, models)..." -ForegroundColor Cyan
$iparams = @()
if ($CpuOnly)   { $iparams += "-CpuOnly" }
if ($SkipModels){ $iparams += "-SkipModels" }
& powershell -NoProfile -ExecutionPolicy Bypass -File $install @iparams
$code = $LASTEXITCODE
if ($code -ne 0) {
  Write-Host "install.ps1 exited with code $code -- see logs/install.log" -ForegroundColor Red
  exit $code
}

# --- 3) Post-install quick checks ---
$Vpy = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $Vpy) {
  Write-Host "Python .venv OK: $Vpy" -ForegroundColor Green
  try {
    $ver = & $Vpy -c "import sys; print(sys.version.split()[0])" 2>$null
    if ($ver) { Write-Host "  Python $ver" -ForegroundColor Gray }
  } catch {}
  try {
    $torch = & $Vpy -c "import torch; print(torch.__version__ + ' cuda=' + str(torch.cuda.is_available()))" 2>$null
    if ($torch) { Write-Host "  PyTorch: $torch" -ForegroundColor Gray }
  } catch {}
} else {
  Write-Host ".venv is missing -- setup incomplete." -ForegroundColor Red
}

# CUDA check (optional)
try {
  nvidia-smi 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) {
    Write-Host "CUDA: nvidia-smi found (GPU present)" -ForegroundColor Green
  } else {
    Write-Host "CUDA: no nvidia-smi (CPU fallback OK)" -ForegroundColor Yellow
  }
} catch {
  Write-Host "CUDA: no nvidia-smi (CPU fallback OK)" -ForegroundColor Yellow
}

# Models check (expected paths; models are NOT in Git, downloaded by install.ps1)
$modelBase = Join-Path $Root "models\Qwen3-TTS-12Hz-1.7B-Base"
$modelCV   = Join-Path $Root "models\Qwen3-TTS-12Hz-1.7B-CustomVoice"
$modelVD   = Join-Path $Root "models\Qwen3-TTS-12Hz-1.7B-VoiceDesign"
Write-Host "Models (expected, not in Git -- downloaded via install.ps1):" -ForegroundColor Cyan
foreach ($m in @($modelBase, $modelCV, $modelVD)) {
  if (Test-Path -LiteralPath $m) {
    Write-Host "  OK   $m" -ForegroundColor Green
  } else {
    Write-Host "  miss (loaded on first start or by manual run): $m" -ForegroundColor Yellow
  }
}
Write-Host "HuggingFace cache alternative: MODELS_DIR/hf/hub/... (see project/app/tts/model_pool.py)" -ForegroundColor Gray

# --- 4) Voice references: frozen-backup read-only import + verify ---
Write-Host ""
Write-Host "== Voice references (cache\voice_refs) ==" -ForegroundColor Cyan
$ImportScript = Join-Path $Root "tools\import_voice_refs_from_frozen_backup.ps1"
if (Test-Path -LiteralPath $ImportScript) {
  Write-Host "Trying read-only import from local Frozen Backup..." -ForegroundColor Gray
  & powershell -NoProfile -ExecutionPolicy Bypass -File $ImportScript 2>&1 | ForEach-Object { Write-Host "  $_" }
  $impCode = $LASTEXITCODE
  if ($impCode -eq 0) {
    Write-Host "  Frozen-backup import: OK." -ForegroundColor Green
  } elseif ($impCode -eq 2) {
    Write-Host "  Frozen backup path not found. That is OK on a new machine;" -ForegroundColor Yellow
    Write-Host "  run import_voice_refs_from_frozen_backup.ps1 manually after placing" -ForegroundColor Yellow
    Write-Host "  the backup, or use materialize_references.py on the GPU host." -ForegroundColor Yellow
  } elseif ($impCode -eq 3) {
    Write-Host "  Frozen backup found but no cache\voice_refs directory inside; skipped." -ForegroundColor Yellow
  } elseif ($impCode -eq 1) {
    Write-Host "  Frozen-backup import finished with missing files (see messages above)." -ForegroundColor Yellow
    Write-Host "  Missing wavs can be materialized via: python tools\materialize_references.py --all-missing" -ForegroundColor Yellow
  } else {
    Write-Host "  Frozen-backup import exited with code $impCode (non-fatal)." -ForegroundColor Yellow
  }
} else {
  Write-Host "  import_voice_refs_from_frozen_backup.ps1 not found; skipping." -ForegroundColor Yellow
}

$Verify = Join-Path $Root "tools\verify_voice_refs.py"
if (Test-Path -LiteralPath $Verify) {
  $Vpy2 = Join-Path $Root ".venv\Scripts\python.exe"
  if (-not (Test-Path -LiteralPath $Vpy2)) { $Vpy2 = "python" }
  Write-Host "Verifying voice references..." -ForegroundColor Gray
  & $Vpy2 $Verify 2>&1 | ForEach-Object { Write-Host "  $_" }
} else {
  Write-Host "  verify_voice_refs.py not found; skipping." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "SETUP complete. Now run:" -ForegroundColor Green
Write-Host "  .\START.bat        (or .\START.ps1)" -ForegroundColor White
Write-Host "  python .\desktop.py" -ForegroundColor White
Write-Host "To reproduce individual voices: python .\tools\reproduce_voice.py --help" -ForegroundColor Gray
