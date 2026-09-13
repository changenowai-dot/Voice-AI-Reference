# ============================================================================
# reproduce_premium.ps1 - Local RTX 5060 reproduction of the premium voices
# ============================================================================
#
# USAGE (PowerShell in repository root or in project/ folder):
#
#   # Only the two locked favorites (voice-09 + voice-12) - priority 1:
#   powershell -ExecutionPolicy Bypass -File project\tools\reproduce_premium.ps1
#
#   # Dry-run (show plan, no GPU):
#   powershell -ExecutionPolicy Bypass -File project\tools\reproduce_premium.ps1 -DryRun
#
#   # All 11 premium voices (EN+DE):
#   powershell -ExecutionPolicy Bypass -File project\tools\reproduce_premium.ps1 -All
#
#   # The 9 remaining shortlist voices (EN voice-22..27 + DE voice-30/32/33/34):
#   powershell -ExecutionPolicy Bypass -File project\tools\reproduce_premium.ps1 -Remaining
#
#   # Selection:
#   powershell -ExecutionPolicy Bypass -File project\tools\reproduce_premium.ps1 -Voices voice-09,voice-12,voice-27,voice-30
#
#   # Per-voice subprocess batch mode (recommended for RTX 5060 8 GB):
#   powershell -ExecutionPolicy Bypass -File project\tools\reproduce_premium.ps1 -Remaining -Batch
#
#   # Post-run validation only (no GPU):
#   powershell -ExecutionPolicy Bypass -File project\tools\reproduce_premium.ps1 -Validate -Remaining
#
#   # With long text from a file:
#   powershell -ExecutionPolicy Bypass -File project\tools\reproduce_premium.ps1 -LongTextFile benchmark\english_longform_benchmark.txt
#
#   # Re-generate existing reference WAVs (not recommended):
#   powershell -ExecutionPolicy Bypass -File project\tools\reproduce_premium.ps1 -NoSkipExisting
#
# PREREQUISITES (one-time):
#   powershell -ExecutionPolicy Bypass -File project\SETUP.ps1
#
# OUTPUTS:
#   project\cache\voice_refs\<voice_id>.wav        - Qwen VoiceDesign reference
#   project\reproduction\<voice_id>\reference_voicedesign.wav - archive copy
#   project\reproduction\<voice_id>\clone_prompt.json           - clone metadata
#   project\reproduction\<voice_id>\test_short.wav              - short test
#   project\reproduction\<voice_id>\test_audition.wav           - audition text
#   project\reproduction\<voice_id>\test_long.wav               - (optional) long
#   project\reproduction\<voice_id>\manifest.json               - provenance
#
# STATUS OF GENERATED FILES: REPRODUCED (never ORIGINAL_RECOVERED).
# The Golden Reference VD-E.wav is never modified.
# Compatible with Windows PowerShell 5.1 (no backtick edge cases, no reserved
# $Args usage, no multi-line quoted inline scripts).
# ============================================================================

[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$All,
    [switch]$Remaining,
    [switch]$Batch,
    [switch]$Validate,
    [string[]]$Voices = @(),
    [string]$LongTextFile = "",
    [switch]$NoSkipExisting,
    [switch]$Force,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

# --- Find project root ------------------------------------------------------
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir  = Split-Path -Parent $ScriptDir   # .../project
$RepoRoot    = Split-Path -Parent $ProjectDir  # .../Voice-AI-Reference

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
    Write-Error "Kein Python gefunden. Bitte zuerst SETUP.ps1 ausfuehren:"
    Write-Error "  powershell -ExecutionPolicy Bypass -File project\SETUP.ps1"
    exit 1
}
Write-Host ("[env] Python: " + $PythonExe) -ForegroundColor Cyan
& $PythonExe --version
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# --- Optional verify torch/CUDA before starting -----------------------------
# Write a small Python probe to a temp file to avoid PS5.1 multi-line string
# parsing issues with embedded quotes / newlines.
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

# --- Build argument list for the Python tool --------------------------------
$ScriptPy = Join-Path $ScriptDir "reproduce_premium.py"
$PyArgs = @($ScriptPy)
if ($Validate) {
    $PyArgs += "--validate"
} elseif ($DryRun) {
    $PyArgs += "--dry-run"
} elseif ($Batch) {
    $PyArgs += "--batch"
    $PyArgs += "--python"
    $PyArgs += $PythonExe
} else {
    $PyArgs += "--reproduce"
}
if ($All) {
    $PyArgs += "--all"
} elseif ($Remaining) {
    $PyArgs += "--remaining"
}
if ($Voices.Count -gt 0) {
    $PyArgs += "--voices"
    $PyArgs += ($Voices -join ",")
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
if ($NoSkipExisting) { $PyArgs += "--no-skip-existing" }
if ($Force)          { $PyArgs += "--force" }

Write-Host ""
Write-Host ("[run] " + $PythonExe + " " + ($PyArgs -join " ")) -ForegroundColor Cyan
Write-Host ""

Push-Location $RepoRoot
try {
    & $PythonExe @PyArgs
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}

Write-Host ""
$outRepro = Join-Path $ProjectDir "reproduction"
$outRefs  = Join-Path $ProjectDir "cache\voice_refs"
if ($code -eq 0) {
    Write-Host "[done] Ausgaben unter:" -ForegroundColor Green
    Write-Host ("  " + $outRepro)
    Write-Host ("  " + $outRefs)
} else {
    Write-Host ("[done] Mindestens eine Stimme fehlgeschlagen (ExitCode " + $code + ").") -ForegroundColor Red
}
exit $code
