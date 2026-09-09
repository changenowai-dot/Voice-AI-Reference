# ============================================================
#  VoiceOverApp — SETUP.ps1 (Einmal-Setup / Preflight)
#
#  Prüft und falls nötig installiert:
#    - Python 3.10–3.13
#    - Virtuelle Umgebung .venv
#    - PyTorch (CUDA 12.8, Blackwell/RTX 50xx) oder CPU-Fallback
#    - Python-Pakete (requirements.txt, qwen-tts)
#    - FFmpeg
#    - Qwen3-TTS-Modelle (1.7B Base / CustomVoice / VoiceDesign)
#
#  Kein Port-Start, keine Transkodierung, nur Setup.
#  Danach: START.bat / START.ps1 / desktop.py
#  UTF-8, Leerzeichen in Pfaden, beliebiges cwd werden korrekt behandelt.
# ============================================================
param(
  [switch]$CpuOnly,
  [switch]$SkipModels
)
$ErrorActionPreference = "Continue"
# UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
try { chcp 65001 | Out-Null } catch {}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
# Handle invocation from any cwd via absolute root
Set-Location $Root
Write-Host "== VoiceOverApp SETUP — Preflight ==" -ForegroundColor Cyan
Write-Host "Root: $Root" -ForegroundColor Gray

# --- 1) Python ---
function Find-Python {
  if (Test-Path ".venv\Scripts\python.exe") { return ".venv\Scripts\python.exe" }
  $cands = @("py -3.12","py -3.11","python3.12","python")
  foreach ($c in $cands) {
    try {
      $exe = $c.Split(" ")[0]; $arg=$c.Split(" ")[1]
      if ($arg) { $out = & $exe $arg -c "import sys; print(sys.executable)" 2>$null }
      else { $out = & $exe -c "import sys; print(sys.executable)" 2>$null }
      if ($out -and -not $out.Contains("WindowsApps")) { return $c }
    } catch {}
  }
  return $null
}
$py = Find-Python
if (-not $py) { Write-Host "Kein Python 3.10-3.13 gefunden — install.ps1 wird es via winget holen." -ForegroundColor Yellow }

# Delegate to install.ps1 (handles venv/deps/CUDA/models, logs to logs/install.log)
$install = Join-Path $Root "install.ps1"
if (-not (Test-Path $install)) { Write-Host "install.ps1 fehlt!" -ForegroundColor Red; exit 1 }
Write-Host "Starte install.ps1 (prüft Python, .venv, deps, CUDA, Modelle)... " -ForegroundColor Cyan
$iparams = @()
if ($CpuOnly) { $iparams += "-CpuOnly" }
if ($SkipModels) { $iparams += "-SkipModels" }
& powershell -NoProfile -ExecutionPolicy Bypass -File $install @iparams
$code = $LASTEXITCODE
if ($code -ne 0) { Write-Host "install.ps1 endete mit Code $code — siehe logs/install.log" -ForegroundColor Red; exit $code }

# --- 2) Quick checks post-install ---
$Vpy = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path $Vpy) {
  Write-Host "Python .venv OK: $Vpy" -ForegroundColor Green
  try { $ver = & $Vpy -c "import sys; print(sys.version.split()[0])"; Write-Host "  Python $ver" -ForegroundColor Gray } catch {}
  try { $torch = & $Vpy -c "import torch; print(torch.__version__, 'cuda='+str(torch.cuda.is_available()))" 2>$null; if ($torch) { Write-Host "  PyTorch: $torch" -ForegroundColor Gray } } catch {}
} else { Write-Host ".venv fehlt — Setup unvollständig." -ForegroundColor Red }
# CUDA check (optional)
try { nvidia-smi 2>$null | Out-Null; if ($LASTEXITCODE -eq 0) { Write-Host "CUDA: nvidia-smi gefunden (GPU vorhanden)" -ForegroundColor Green } else { Write-Host "CUDA: kein nvidia-smi (CPU-Fallback OK)" -ForegroundColor Yellow } } catch { Write-Host "CUDA: kein nvidia-smi (CPU-Fallback OK)" -ForegroundColor Yellow }
# Models check (expected paths, not in Git)
$modelBase = Join-Path $Root "models/Qwen3-TTS-12Hz-1.7B-Base"
$modelCV   = Join-Path $Root "models/Qwen3-TTS-12Hz-1.7B-CustomVoice"
$modelVD   = Join-Path $Root "models/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
# Also check HF cache alternative (project/app/tts/model_pool.py)
Write-Host "Modelle (erwartet, nicht im Git — Download via install.ps1):" -ForegroundColor Cyan
foreach ($m in @($modelBase,$modelCV,$modelVD)) {
  if (Test-Path $m) { Write-Host "  OK  $m" -ForegroundColor Green } else { Write-Host "  fehlt (wird bei erstem Start nachgeladen oder manuell): $m" -ForegroundColor Yellow }
}
Write-Host "HuggingFace-Cache Alternative: MODELS_DIR/hf/hub/... (vgl. project/app/tts/model_pool.py)" -ForegroundColor Gray
Write-Host ""
Write-Host "SETUP abgeschlossen. Starte jetzt:" -ForegroundColor Green
Write-Host "  .\START.bat        (oder .\START.ps1)" -ForegroundColor White
Write-Host "  python .\desktop.py" -ForegroundColor White
Write-Host "Für Reproduktion einzelner Stimmen: python project/tools/reproduce_voice.py --help" -ForegroundColor Gray
