<#
.SYNOPSIS
  Importiert Voice-Referenz-WAVs + Sidecar-Manifeste aus dem FROZEN
  Teil-A-Backup in diesen Teil-A-Gesamtstand.

.DESCRIPTION
  Das Skript liest NUR aus dem Frozen-Backup (niemals schreibend)
  und kopiert fehlende Referenzen nach project\cache\voice_refs\.

  Es wird BENÖTIGT, weil Cache-WAVs (cache\voice_refs\*.wav)
  nicht in Git getrackt sind (Laufzeit-Materialisierungsprodukte),
  aber auf dem Windows-Rechner im Frozen Backup vorliegen. Nach
  einmaligem Import ist der Teil-A-Download in sich geschlossen.

  Die Golden Reference VD-E.wav (SHA B156C02A...) wird separat
  gegen ihren bekannten Hash geprüft und NUR bei korrektem Hash
  übernommen (niemals überschrieben, falls bereits vorhanden und
  identisch).

.EXAMPLE
  # Nur Prüfen, nichts kopieren:
  powershell -ExecutionPolicy Bypass -File tools\import_voice_refs_from_frozen_backup.ps1 -WhatIf

  # Import mit Standard-Pfad:
  powershell -ExecutionPolicy Bypass -File tools\import_voice_refs_from_frozen_backup.ps1

  # Anderer Frozen-Pfad:
  powershell -ExecutionPolicy Bypass -File tools\import_voice_refs_from_frozen_backup.ps1 -FrozenBackupRoot "C:\pfad\zu\VoiceOverApp_STAND_A_PHASE2_..."
#>
[CmdletBinding()]
param(
    [string]$FrozenBackupRoot = "C:\Users\johan\OneDrive\Desktop\fertige projekte\TEST Apps\VoiceOverApp_STAND_A_PHASE2_20260919_061843",
    [switch]$WhatIf,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# --- paths -----------------------------------------------------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
$VoiceRefsDir = Join-Path $ProjectRoot "cache\voice_refs"
$ExpectedRefsJson = Join-Path $ProjectRoot "tools\expected_voice_refs.json"

$VDE_EXPECTED_SHA256 = "B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025"

# --- sanity checks ---------------------------------------------------
if (-not (Test-Path $ExpectedRefsJson)) {
    throw "expected_voice_refs.json nicht gefunden unter $ExpectedRefsJson"
}
$Expected = Get-Content $ExpectedRefsJson -Raw -Encoding UTF8 | ConvertFrom-Json
$CloneVoices = @($Expected | Where-Object { -not $_.customvoice })
Write-Host "[INFO] Expected clone voices: $($CloneVoices.Count)"

if (-not (Test-Path $FrozenBackupRoot)) {
    Write-Host "[WARN] Frozen-Backup-Pfad nicht gefunden: $FrozenBackupRoot"
    Write-Host "[INFO] Keine Referenzen importiert. Starte materialize_*.ps1 auf dem GPU-Host, um die fehlenden WAVs via VoiceDesign zu erzeugen."
    exit 2   # signals "backup not present"
}

Write-Host "[INFO] Frozen Backup Root: $FrozenBackupRoot"
$FrozenProject = Join-Path $FrozenBackupRoot "project"
if (-not (Test-Path $FrozenProject)) { $FrozenProject = $FrozenBackupRoot }
$FrozenVoiceRefs = Join-Path $FrozenProject "cache\voice_refs"
if (-not (Test-Path $FrozenVoiceRefs)) {
    # scan for a voice_refs directory anywhere under frozen root
    $hit = Get-ChildItem -Path $FrozenBackupRoot -Recurse -Directory -Filter voice_refs -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($hit) { $FrozenVoiceRefs = $hit.FullName }
}
if (-not (Test-Path $FrozenVoiceRefs)) {
    Write-Host "[ERROR] Kein cache\voice_refs\ Verzeichnis im Frozen Backup gefunden."
    exit 3
}
Write-Host "[INFO] Frozen voice_refs: $FrozenVoiceRefs"

if (-not $WhatIf) { New-Item -ItemType Directory -Force -Path $VoiceRefsDir | Out-Null }

function Get-FileSHA256([string]$Path) {
    $h = [System.Security.Cryptography.SHA256]::Create()
    try {
        $s = [System.IO.File]::OpenRead($Path)
        try { return ([BitConverter]::ToString($h.ComputeHash($s)) -replace "-", "").ToLowerInvariant() }
        finally { $s.Dispose() }
    } finally { $h.Dispose() }
}

# --- import loop -----------------------------------------------------
$copied = 0; $present = 0; $missing = 0; $manifestPresent = 0; $manifestMissing = 0; $errors = 0

foreach ($v in $CloneVoices) {
    $rel = $v.ref_path     # e.g. cache/voice_refs/XYZ.wav
    if (-not $rel) {
        # VD-E has ref_path
        if ($v.voice_id -eq "vd_e") { $rel = "cache/voice_refs/VD-E.wav" }
        else { Write-Host "[SKIP] $($v.voice_id) – keine ref_path Angabe"; continue }
    }
    $fname = Split-Path $rel -Leaf
    $src = Join-Path $FrozenVoiceRefs $fname
    $dst = Join-Path $VoiceRefsDir $fname
    $srcJson = "$src.json"
    $dstJson = "$dst.json"

    # Golden reference special-case
    if ($v.voice_id -eq "vd_e") {
        if (Test-Path $dst) {
            $curSha = Get-FileSHA256 $dst
            if ($curSha -ieq $VDE_EXPECTED_SHA256) {
                Write-Host "[HOLD] VD-E.wav bereits vorhanden und SHA-korrekt (GOLDEN-REF-SCHUTZ)."
                $present++; continue
            }
            Write-Host "[ERROR] VD-E.wav existiert, aber SHA weicht ab! Datei wird NICHT überschrieben. Bitte manuell prüfen."
            $errors++; continue
        }
        if (-not (Test-Path $src)) {
            Write-Host "[MISS] VD-E.wav nicht im Frozen Backup."; $missing++; continue
        }
        $srcSha = Get-FileSHA256 $src
        if ($srcSha -ine $VDE_EXPECTED_SHA256) {
            Write-Host "[ERROR] VD-E.wav im Frozen Backup hat falschen SHA ($srcSha). Erwartet $VDE_EXPECTED_SHA256. Import ABGELEHNT."
            $errors++; continue
        }
        if ($WhatIf) { Write-Host "[WOULD-COPY] VD-E.wav (GOLDEN-REF, SHA OK)" }
        else { Copy-Item -LiteralPath $src -Destination $dst -Force; Write-Host "[OK] VD-E.wav (GOLDEN-REF, SHA validiert)" }
        $copied++; continue
    }

    if (Test-Path $dst) {
        # already present, leave alone
        $present++
    }
    else {
        if (Test-Path $src) {
            if ($WhatIf) { Write-Host "[WOULD-COPY] $fname" }
            else { Copy-Item -LiteralPath $src -Destination $dst -Force }
            $copied++
        }
        else {
            Write-Host "[MISS] $fname nicht im Frozen Backup (Stimme: $($v.voice_id), Status: $($v.status))."
            $missing++
        }
    }

    # sidecar manifest
    if (Test-Path $dstJson) { $manifestPresent++ }
    elseif (Test-Path $srcJson) {
        if ($WhatIf) { Write-Host "[WOULD-COPY] $fname.json" }
        else { Copy-Item -LiteralPath $srcJson -Destination $dstJson -Force }
        $manifestPresent++
    }
    else {
        $manifestMissing++
    }
}

Write-Host ""
Write-Host "===== Import-Zusammenfassung ====="
Write-Host "  Kopiert:                $copied"
Write-Host "  Bereits vorhanden:      $present"
Write-Host "  Im Backup GEFUNDET:     $($copied+$present)"
Write-Host "  Auch im Backup FEHLEND: $missing"
Write-Host "  Sidecar-Manifeste da:   $manifestPresent"
Write-Host "  Sidecar-Manifeste fehl: $manifestMissing"
Write-Host "  Fehler:                 $errors"

if ($missing -gt 0 -or $errors -gt 0) {
    Write-Host ""
    Write-Host "[HINWEIS] Fehlende WAVs koennen auf dem GPU-Host materialisiert werden via:"
    Write-Host "           python project\tools\materialize_references.py --all-missing"
    Write-Host "         Bereits vorhandene WAVs werden dabei NICHT ueberschrieben."
    exit 1
}

Write-Host "[DONE] Alle im Frozen Backup vorhandenen Referenzen wurden importiert."
exit 0
