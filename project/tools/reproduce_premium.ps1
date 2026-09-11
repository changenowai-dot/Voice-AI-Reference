# ============================================================================
# reproduce_premium.ps1 — Lokale RTX 5060 Reproduktion der Premium-Stimmen
# ============================================================================
#
# BENUTZUNG (PowerShell im Repository-Root oder im project/-Ordner):
#
#   # Nur die zwei gesperrten Favoriten (voice-09 + voice-12) — Priorität 1:
#   powershell -ExecutionPolicy Bypass -File project\tools\reproduce_premium.ps1
#
#   # Dry-run (Plan anzeigen, keine GPU):
#   powershell -ExecutionPolicy Bypass -File project\tools\reproduce_premium.ps1 -DryRun
#
#   # Alle 7 Premium-Stimmen:
#   powershell -ExecutionPolicy Bypass -File project\tools\reproduce_premium.ps1 -All
#
#   # Nur eine Auswahl:
#   powershell -ExecutionPolicy Bypass -File project\tools\reproduce_premium.ps1 -Voices voice-09,voice-12,voice-27
#
#   # Mit Langtext:
#   powershell -ExecutionPolicy Bypass -File project\tools\reproduce_premium.ps1 -LongTextFile benchmark\english_longform_benchmark.txt
#
#   # Vorhandene Reference WAVs neu erzeugen (nicht empfohlen — ändert Seeds nicht,
#   # kann aber eine beschädigte Datei ersetzen):
#   powershell -ExecutionPolicy Bypass -File project\tools\reproduce_premium.ps1 -NoSkipExisting
#
# VORAUSSETZUNGEN (vor dem ersten Lauf einmal):
#   powershell -ExecutionPolicy Bypass -File project\SETUP.ps1
#
# AUSGABEN:
#   project\cache\voice_refs\<voice_id>.wav      — Qwen VoiceDesign Referenz
#   project\reproduction\<voice_id>\reference_voicedesign.wav — Archivkopie
#   project\reproduction\<voice_id>\clone_prompt.json         — Clone-Metadaten
#   project\reproduction\<voice_id>\test_short.wav            — Kurztest
#   project\reproduction\<voice_id>\test_audition.wav         — Audition-Text
#   project\reproduction\<voice_id>\test_long.wav             — (optional) Lang
#   project\reproduction\<voice_id>\manifest.json             — Provenienz
#
# STATUS DER ERZEUGTEN DATEIEN: REPRODUCED (niemals ORIGINAL_RECOVERED)
# Die Golden Reference VD-E.wav wird unter keinen Umständen verändert.
# ============================================================================

[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$All,
    [string[]]$Voices = @(),
    [string]$LongTextFile = "",
    [switch]$NoSkipExisting,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

# --- Find project root ------------------------------------------------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir   # .../project
$RepoRoot = Split-Path -Parent $ProjectDir    # .../Voice-AI-Reference

if ($Help) {
    Get-Help $MyInvocation.MyCommand.Path -Full
    exit 0
}

# --- Resolve Python executable (project-local venv preferred) ---------------
$PythonExe = $null
$VenvPy = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (Test-Path $VenvPy) {
    $PythonExe = $VenvPy
} else {
    # Fall back to system python
    $pyCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pyCmd) { $pyCmd = Get-Command py -ErrorAction SilentlyContinue }
    if ($pyCmd) { $PythonExe = $pyCmd.Source }
}
if (-not $PythonExe) {
    Write-Error "Kein Python gefunden. Bitte zuerst SETUP.ps1 ausführen:"
    Write-Error "  powershell -ExecutionPolicy Bypass -File project\SETUP.ps1"
    exit 1
}
Write-Host "[env] Python: $PythonExe" -ForegroundColor Cyan
& $PythonExe --version

# --- Optional verify torch/CUDA before starting -----------------------------
if (-not $DryRun) {
    Write-Host "[env] Prüfe CUDA/torch/qwen-tts..." -ForegroundColor Cyan
    $envCheck = & $PythonExe -c "import sys; ok=True
try:
 import torch; print(f'torch={torch.__version__} cuda={torch.cuda.is_available()} dev={torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"none\"}')
except Exception as e:
 print(f'torch fehlt: {e}'); ok=False
try:
 import qwen_tts; print(f'qwen_tts OK')
except Exception as e:
 print(f'qwen_tts fehlt: {e}'); ok=False
sys.exit(0 if ok else 3)" 2>&1
    $envCheck | ForEach-Object { Write-Host "  $_" }
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Umgebung unvollständig — SETUP.ps1 ausführen."
        exit $LASTEXITCODE
    }
}

# --- Build argument list ----------------------------------------------------
$Script = Join-Path $ScriptDir "reproduce_premium.py"
$Args = @($Script)
if ($DryRun) { $Args += "--dry-run" }
else         { $Args += "--reproduce" }
if ($All)    { $Args += "--all" }
if ($Voices.Count -gt 0) {
    $Args += "--voices"
    $Args += ($Voices -join ",")
}
if ($LongTextFile) {
    if (-not (Test-Path $LongTextFile)) {
        # Try relative to RepoRoot
        $alt = Join-Path $RepoRoot $LongTextFile
        if (Test-Path $alt) { $LongTextFile = $alt }
        else { Write-Error "LongTextFile nicht gefunden: $LongTextFile"; exit 1 }
    }
    $Args += "--long-text"
    $Args += "@$((Resolve-Path $LongTextFile).Path)"
}
if ($NoSkipExisting) { $Args += "--no-skip-existing" }

Write-Host ""
Write-Host "[run] & $PythonExe $($Args -join ' ')" -ForegroundColor Cyan
Write-Host ""

Push-Location $RepoRoot
try {
    & $PythonExe @Args
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}

Write-Host ""
if ($code -eq 0) {
    Write-Host "[done] Ausgaben unter:" -ForegroundColor Green
    Write-Host "  $(Join-Path $ProjectDir 'reproduction')"
    Write-Host "  $(Join-Path $ProjectDir 'cache\voice_refs')"
} else {
    Write-Host "[done] Mindestens eine Stimme fehlgeschlagen (ExitCode $code)." -ForegroundColor Red
}
exit $code
