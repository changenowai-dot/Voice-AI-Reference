# ============================================================
#  VoiceOverApp -- SETUP.ps1 (Repo-Root Wrapper)
#  Delegiert an project/SETUP.ps1 -- ASCII-only, kein Unicode
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
$inner = Join-Path $Root "project\SETUP.ps1"
if (Test-Path -LiteralPath $inner) {
  $iparams = @()
  if ($CpuOnly) { $iparams += "-CpuOnly" }
  if ($SkipModels) { $iparams += "-SkipModels" }
  & powershell -NoProfile -ExecutionPolicy Bypass -File $inner @iparams
  exit $LASTEXITCODE
}
# Fallback: falls project/SETUP.ps1 nicht gefunden, lokale Logik (wie project/SETUP.ps1)
Set-Location -LiteralPath $Root
Write-Host "== VoiceOverApp SETUP -- Preflight (Root Fallback) ==" -ForegroundColor Cyan
Write-Host "Root: $Root" -ForegroundColor Gray
function Find-Python {
  if (Test-Path -LiteralPath ".venv\Scripts\python.exe") { return ".venv\Scripts\python.exe" }
  $cands = @("py -3.12","py -3.11","python3.12","python")
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
      if ($out -and -not $out.Contains("WindowsApps")) { return $c }
    } catch {}
  }
  return $null
}
$py = Find-Python
if (-not $py) { Write-Host "Kein Python 3.10-3.13 gefunden -- install.ps1 wird es via winget holen." -ForegroundColor Yellow }
$install = Join-Path $Root "project\install.ps1"
if (-not (Test-Path -LiteralPath $install)) { $install = Join-Path $Root "install.ps1" }
if (-not (Test-Path -LiteralPath $install)) { Write-Host "install.ps1 fehlt!" -ForegroundColor Red; exit 1 }
Write-Host "Starte install.ps1 ..." -ForegroundColor Cyan
$iparams = @()
if ($CpuOnly) { $iparams += "-CpuOnly" }
if ($SkipModels) { $iparams += "-SkipModels" }
& powershell -NoProfile -ExecutionPolicy Bypass -File $install @iparams
exit $LASTEXITCODE
