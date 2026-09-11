# ============================================================================
# reproduce_batch.ps1 - Sequential batch reproduction for RTX 5060 (8 GB VRAM)
# ============================================================================
#
# Runs reproduce_premium.py in --batch mode: one Python SUBPROCESS per voice,
# guaranteeing full CUDA / torch / model-pool teardown between voices. On
# individual failure it continues with the next voice and prints a final
# summary, then optionally runs the post-run validator.
#
# USAGE (PowerShell in repository root):
#
#   # Default batch: the 9 remaining shortlist voices (EN voice-22..27 then
#   # DE voice-30/32/33/34) — this phase. Already-done voices (voice-09/12)
#   # are skipped and their outputs are NOT touched.
#   powershell -ExecutionPolicy Bypass -File project\tools\reproduce_batch.ps1
#
#   # All 11 voices (existing voice-09/12 skipped):
#   powershell -ExecutionPolicy Bypass -File project\tools\reproduce_batch.ps1 -All
#
#   # Custom selection:
#   powershell -ExecutionPolicy Bypass -File project\tools\reproduce_batch.ps1 -Voices voice-22,voice-30
#
#   # Skip validator at the end:
#   powershell -ExecutionPolicy Bypass -File project\tools\reproduce_batch.ps1 -NoValidate
#
#   # Dry-run (plan only, no GPU):
#   powershell -ExecutionPolicy Bypass -File project\tools\reproduce_batch.ps1 -DryRun
#
#   # Force regenerate even already-REPRODUCED voices (not recommended):
#   powershell -ExecutionPolicy Bypass -File project\tools\reproduce_batch.ps1 -Force
#
# OUTPUTS are written to project\reproduction\<voice_id>\ and
# project\cache\voice_refs\<voice_id>.wav, exactly like reproduce_premium.ps1.
#
# Compatible with Windows PowerShell 5.1.
# ============================================================================

[CmdletBinding()]
param(
    [switch]$All,
    [switch]$Remaining,
    [string[]]$Voices = @(),
    [string]$LongTextFile = "",
    [switch]$NoValidate,
    [switch]$DryRun,
    [switch]$Force,
    [switch]$NoSkipExisting,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

# --- Find project root ------------------------------------------------------
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir   # .../project
$RepoRoot   = Split-Path -Parent $ProjectDir  # .../Voice-AI-Reference

if ($Help) {
    Get-Help $MyInvocation.MyCommand.Path -Full
    exit 0
}

# --- Resolve Python executable ----------------------------------------------
$PythonExe = $null
$VenvPy = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (Test-Path $VenvPy) {
    $PythonExe = $VenvPy
} else {
    $pyCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pyCmd) { $pyCmd = Get-Command py -ErrorAction SilentlyContinue }
    if ($pyCmd) { $PythonExe = $pyCmd.Source }
}
if (-not $PythonExe) {
    Write-Error "Kein Python gefunden. Bitte zuerst SETUP.ps1 ausfuehren:"
    Write-Error "  powershell -ExecutionPolicy Bypass -File project\SETUP.ps1"
    exit 1
}
Write-Host ("[env] Python: " + $PythonExe) -ForegroundColor Cyan
& $PythonExe --version
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# --- Environment probe (skip on dry-run) ------------------------------------
if (-not $DryRun) {
    Write-Host "[env] Pruefe CUDA/torch/qwen-tts..." -ForegroundColor Cyan
    $ProbePy = Join-Path $env:TEMP ("voiceover_envcheck_" + [guid]::NewGuid().ToString("N") + ".py")
    $ProbeSrc = @'
import sys
ok = True
try:
    import torch
    if torch.cuda.is_available():
        print("torch={0} cuda=1 dev={1}".format(torch.__version__, torch.cuda.get_device_name(0)))
    else:
        print("torch={0} cuda=0 dev=none".format(torch.__version__))
except Exception as e:
    print("torch fehlt: {0}".format(e))
    ok = False
try:
    import qwen_tts  # noqa: F401
    print("qwen_tts OK")
except Exception as e:
    print("qwen_tts fehlt: {0}".format(e))
    ok = False
sys.exit(0 if ok else 3)
'@
    Set-Content -Path $ProbePy -Value $ProbeSrc -Encoding UTF8
    try {
        & $PythonExe $ProbePy 2>&1 | ForEach-Object { Write-Host ("  " + $_) }
        $probeCode = $LASTEXITCODE
    } finally {
        if (Test-Path $ProbePy) { Remove-Item $ProbePy -Force }
    }
    if ($probeCode -ne 0) {
        Write-Error "Umgebung unvollstaendig - SETUP.ps1 ausfuehren."
        exit $probeCode
    }
}

# --- Build Python args ------------------------------------------------------
$ScriptPy = Join-Path $ScriptDir "reproduce_premium.py"

if ($DryRun) {
    $PyArgs = @($ScriptPy, "--dry-run")
} else {
    $PyArgs = @($ScriptPy, "--batch", "--python", $PythonExe)
}
if ($All) {
    $PyArgs += "--all"
} elseif ($Voices.Count -gt 0) {
    $PyArgs += "--voices"
    $PyArgs += ($Voices -join ",")
} else {
    # Default: --remaining (the 9 shortlist voices for this phase)
    $PyArgs += "--remaining"
}
if ($LongTextFile) {
    $resolved = $LongTextFile
    if (-not (Test-Path $resolved)) {
        $alt = Join-Path $RepoRoot $LongTextFile
        if (Test-Path $alt) { $resolved = $alt }
        else { Write-Error ("LongTextFile nicht gefunden: " + $LongTextFile); exit 1 }
    }
    $fullPath = (Resolve-Path $resolved).Path
    $PyArgs += "--long-text"
    $PyArgs += ("@" + $fullPath)
}
if ($Force)           { $PyArgs += "--force" }
if ($NoSkipExisting)  { $PyArgs += "--no-skip-existing" }

Write-Host ""
Write-Host ("[run] " + $PythonExe + " " + ($PyArgs -join " ")) -ForegroundColor Cyan
Write-Host ""

Push-Location $RepoRoot
try {
    & $PythonExe @PyArgs
    $batchCode = $LASTEXITCODE
} finally {
    Pop-Location
}

Write-Host ""

# --- Post-run validator -----------------------------------------------------
$validateScope = "--all"
if (-not $All -and $Voices.Count -eq 0) { $validateScope = "--remaining" }
elseif ($Voices.Count -gt 0) { $validateVoiceArg = $Voices -join "," }

if (-not $DryRun -and -not $NoValidate) {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "POST-RUN VALIDATION" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    $ValArgs = @($ScriptPy, "--validate")
    if ($Voices.Count -gt 0) {
        $ValArgs += "--voices"
        $ValArgs += ($Voices -join ",")
    } elseif ($All) {
        $ValArgs += "--all"
    } else {
        $ValArgs += "--remaining"
    }
    Push-Location $RepoRoot
    try {
        & $PythonExe @ValArgs
        $valCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
} else {
    $valCode = 0
}

$outRepro = Join-Path $ProjectDir "reproduction"
$outRefs  = Join-Path $ProjectDir "cache\voice_refs"
Write-Host ""
if ($batchCode -eq 0 -and $valCode -eq 0) {
    Write-Host "[done] BATCH OK + Validierung OK" -ForegroundColor Green
    Write-Host ("  " + $outRepro)
    Write-Host ("  " + $outRefs)
} else {
    Write-Host ("[done] BATCH ExitCode=" + $batchCode + "  VALIDATION ExitCode=" + $valCode) -ForegroundColor Yellow
    Write-Host ("  Ausgaben unter: " + $outRepro)
    Write-Host ("  Referenz-WAVs:  " + $outRefs)
}
exit $batchCode
