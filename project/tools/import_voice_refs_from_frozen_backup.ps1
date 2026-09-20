<#
.SYNOPSIS
  Read-only importer for voice reference WAVs + sidecar manifests from
  the user's frozen PART-A backup into this PART-A tree.

.DESCRIPTION
  Reads ONLY from the frozen backup (never writes to it) and copies
  missing references into project\cache\voice_refs\.

  Required because cache\voice_refs\*.wav are runtime materialization
  products (never tracked in git) but exist on the user's Windows PC
  inside the frozen backup. After a single import the PART-A download
  is self-contained.

  Golden reference VD-E.wav is validated against its pinned SHA-256 and
  is NEVER overwritten if it already exists with the correct hash.

  Exit codes:
    0 = all expected clone refs copied (nothing was missing in backup)
    1 = some expected WAVs were still missing in the backup
    2 = frozen backup root path not found
    3 = frozen backup has no cache\voice_refs directory
    4 = I/O or argument error

.EXAMPLE
  # Dry-run (plan, no copy):
  powershell -ExecutionPolicy Bypass -File tools\import_voice_refs_from_frozen_backup.ps1 -WhatIf

  # Import with default path:
  powershell -ExecutionPolicy Bypass -File tools\import_voice_refs_from_frozen_backup.ps1

  # Custom frozen-backup path:
  powershell -ExecutionPolicy Bypass -File tools\import_voice_refs_from_frozen_backup.ps1 `
      -FrozenBackupRoot "C:\path\to\VoiceOverApp_STAND_A_PHASE2_20260919_061843"
#>
[CmdletBinding()]
param(
    [string]$FrozenBackupRoot = "C:\Users\johan\OneDrive\Desktop\fertige projekte\TEST Apps\VoiceOverApp_STAND_A_PHASE2_20260919_061843",
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

# --- paths -----------------------------------------------------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
$VoiceRefsDir = Join-Path $ProjectRoot "cache\voice_refs"
$ExpectedRefsJson = Join-Path $ScriptDir "expected_voice_refs.json"

# Golden reference pinned SHA-256 (lower-case, no separators)
$script:VDE_EXPECTED_SHA256 = "b156c02a60a873ad95fc92390c4a136c85308b20188373cd734bee5e5e5f2025"

# --- sanity checks ---------------------------------------------------
if (-not (Test-Path -LiteralPath $ExpectedRefsJson)) {
    Write-Host "[ERROR] expected_voice_refs.json not found at $ExpectedRefsJson" -ForegroundColor Red
    exit 4
}
$Expected = Get-Content -LiteralPath $ExpectedRefsJson -Raw -Encoding UTF8 | ConvertFrom-Json
$CloneVoices = @($Expected | Where-Object { -not $_.customvoice })
Write-Host "[INFO] Expected clone voices: $($CloneVoices.Count)"

if (-not (Test-Path -LiteralPath $FrozenBackupRoot)) {
    Write-Host "[WARN] Frozen backup path not found: $FrozenBackupRoot"
    Write-Host "[INFO] No references imported. Run materialize_references.py on the GPU host"
    Write-Host "       to generate missing WAVs via VoiceDesign."
    exit 2
}
Write-Host "[INFO] Frozen backup root: $FrozenBackupRoot"

$FrozenProject = Join-Path $FrozenBackupRoot "project"
if (-not (Test-Path -LiteralPath $FrozenProject)) { $FrozenProject = $FrozenBackupRoot }
$FrozenVoiceRefs = Join-Path $FrozenProject "cache\voice_refs"
if (-not (Test-Path -LiteralPath $FrozenVoiceRefs)) {
    $hit = Get-ChildItem -LiteralPath $FrozenBackupRoot -Recurse -Directory -Filter voice_refs -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($hit) { $FrozenVoiceRefs = $hit.FullName }
}
if (-not (Test-Path -LiteralPath $FrozenVoiceRefs)) {
    Write-Host "[ERROR] No cache\voice_refs directory found inside the frozen backup."
    exit 3
}
Write-Host "[INFO] Frozen voice_refs: $FrozenVoiceRefs"
Write-Host "[INFO] Target voice_refs: $VoiceRefsDir"

if (-not $WhatIf) {
    New-Item -ItemType Directory -Force -Path $VoiceRefsDir | Out-Null
}

function Get-FileSHA256([string]$Path) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $fs = [System.IO.File]::OpenRead($Path)
        try {
            $hashBytes = $sha.ComputeHash($fs)
        } finally {
            $fs.Dispose()
        }
    } finally {
        $sha.Dispose()
    }
    return ([BitConverter]::ToString($hashBytes) -replace "-", "").ToLowerInvariant()
}

# --- import loop -----------------------------------------------------
$copied = 0
$present = 0
$missing = 0
$manifestPresent = 0
$manifestMissing = 0
$errors = 0

foreach ($v in $CloneVoices) {
    $rel = $v.ref_path
    if (-not $rel) {
        if ($v.voice_id -eq "vd_e") {
            $rel = "cache/voice_refs/VD-E.wav"
        } else {
            Write-Host "[SKIP] $($v.voice_id) -- no ref_path set"
            continue
        }
    }
    $fname = Split-Path -Leaf $rel
    $src = Join-Path $FrozenVoiceRefs $fname
    $dst = Join-Path $VoiceRefsDir $fname
    $srcJson = "$src.json"
    $dstJson = "$dst.json"

    # ---- Golden reference (VD-E) special-case ----
    if ($v.voice_id -eq "vd_e") {
        if (Test-Path -LiteralPath $dst) {
            $curSha = Get-FileSHA256 $dst
            if ($curSha -ieq $script:VDE_EXPECTED_SHA256) {
                Write-Host "[HOLD] VD-E.wav already present and SHA matches (GOLDEN REF PROTECTED)."
                $present++
                continue
            }
            Write-Host "[ERROR] VD-E.wav exists but its SHA does NOT match the pinned golden-ref hash." -ForegroundColor Red
            Write-Host "        Existing SHA: $curSha" -ForegroundColor Red
            Write-Host "        Expected SHA: $($script:VDE_EXPECTED_SHA256)" -ForegroundColor Red
            Write-Host "        File will NOT be overwritten. Please investigate manually." -ForegroundColor Red
            $errors++
            continue
        }
        if (-not (Test-Path -LiteralPath $src)) {
            Write-Host "[MISS] VD-E.wav not present in frozen backup." -ForegroundColor Red
            $missing++
            continue
        }
        $srcSha = Get-FileSHA256 $src
        if ($srcSha -ine $script:VDE_EXPECTED_SHA256) {
            Write-Host "[ERROR] VD-E.wav in frozen backup has wrong SHA ($srcSha)." -ForegroundColor Red
            Write-Host "        Expected: $($script:VDE_EXPECTED_SHA256)" -ForegroundColor Red
            Write-Host "        Import REJECTED to protect the golden reference." -ForegroundColor Red
            $errors++
            continue
        }
        if ($WhatIf) {
            Write-Host "[WOULD-COPY] VD-E.wav (GOLDEN REF, SHA validated)"
        } else {
            Copy-Item -LiteralPath $src -Destination $dst -Force
            Write-Host "[OK] VD-E.wav (GOLDEN REF, SHA validated)" -ForegroundColor Green
        }
        $copied++
        continue
    }

    # ---- Regular clone voice ----
    if (Test-Path -LiteralPath $dst) {
        $present++
    } else {
        if (Test-Path -LiteralPath $src) {
            if ($WhatIf) {
                Write-Host "[WOULD-COPY] $fname"
            } else {
                Copy-Item -LiteralPath $src -Destination $dst -Force
            }
            $copied++
        } else {
            Write-Host "[MISS] $fname not in frozen backup (voice: $($v.voice_id), status: $($v.status))."
            $missing++
        }
    }

    # sidecar .wav.json manifest
    if (Test-Path -LiteralPath $dstJson) {
        $manifestPresent++
    } elseif (Test-Path -LiteralPath $srcJson) {
        if ($WhatIf) {
            Write-Host "[WOULD-COPY] $fname.json"
        } else {
            Copy-Item -LiteralPath $srcJson -Destination $dstJson -Force
        }
        $manifestPresent++
    } else {
        $manifestMissing++
    }
}

Write-Host ""
Write-Host "===== Import summary ====="
Write-Host "  Copied:                  $copied"
Write-Host "  Already present:         $present"
Write-Host "  Found in backup:         $($copied + $present)"
Write-Host "  Still missing after run: $missing"
Write-Host "  Sidecar manifests OK:    $manifestPresent"
Write-Host "  Sidecar manifests miss:  $manifestMissing"
Write-Host "  Errors:                  $errors"

if ($errors -gt 0) {
    Write-Host ""
    Write-Host "[FAIL] Golden reference protection error -- aborting." -ForegroundColor Red
    exit 4
}
if ($missing -gt 0) {
    Write-Host ""
    Write-Host "[INFO] Missing WAVs can be generated on the GPU host via:"
    Write-Host "         python project\tools\materialize_references.py --all-missing"
    Write-Host "       Existing WAVs will NOT be overwritten."
    exit 1
}
Write-Host "[DONE] All clone references found in the frozen backup were imported." -ForegroundColor Green
exit 0
