# ============================================================
# compute_audio_hashes.ps1
# Compute SHA-256 hashes for Phase 4 audio artifacts
# Run on the local RTX 5060 machine after benchmark
# ============================================================

$ErrorActionPreference = "Stop"

$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}
$RepoRoot = Split-Path -Parent $ScriptDir
$OutputDir = Join-Path $RepoRoot "project\output"
$ManifestPath = Join-Path $ScriptDir "audio_hashes_20260906_210750.json"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Phase 4 Audio Hash Computation" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Repo:    $RepoRoot" -ForegroundColor Gray
Write-Host "Output:  $OutputDir" -ForegroundColor Gray
Write-Host "Run-ID:  20260906_210750" -ForegroundColor Gray
Write-Host ""

$variants = @(
    @{ Name = "Baseline"; Dir = "phase4_baseline" }
    @{ Name = "A"; Dir = "phase4_A" }
    @{ Name = "B"; Dir = "phase4_B" }
    @{ Name = "E"; Dir = "phase4_E" }
    @{ Name = "C"; Dir = "phase4_C" }
    @{ Name = "D"; Dir = "phase4_variant_D" }
)

$results = @{
    run_id = "20260906_210750"
    computed_at = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
    hardware = "NVIDIA GeForce RTX 5060"
    output_base = $OutputDir
    variants = @()
}

foreach ($v in $variants) {
    $vdir = Join-Path $OutputDir $v.Dir
    Write-Host "Variant $($v.Name): $vdir" -ForegroundColor Yellow

    if (-not (Test-Path $vdir)) {
        Write-Host "  [MISSING] Directory not found" -ForegroundColor Red
        $results.variants += @{
            variant = $v.Name
            directory = $v.Dir
            status = "MISSING"
            files = @()
        }
        continue
    }

    $wavFiles = Get-ChildItem $vdir -Filter "*.wav" -ErrorAction SilentlyContinue
    if ($wavFiles.Count -eq 0) {
        Write-Host "  [EMPTY] No WAV files found" -ForegroundColor DarkYellow
        $results.variants += @{
            variant = $v.Name
            directory = $v.Dir
            status = "EMPTY"
            files = @()
        }
        continue
    }

    $fileHashes = @()
    foreach ($wf in $wavFiles) {
        $hash = (Get-FileHash -Path $wf.FullName -Algorithm SHA256).Hash
        $sizeMB = [math]::Round($wf.Length / (1024 * 1024), 3)
        Write-Host "  [OK] $($wf.Name) | $sizeMB MB | SHA256: $hash" -ForegroundColor Green
        $fileHashes += @{
            filename = $wf.Name
            path = $wf.FullName
            size_bytes = $wf.Length
            size_mb = $sizeMB
            sha256 = $hash
        }
    }

    $results.variants += @{
        variant = $v.Name
        directory = $v.Dir
        status = "OK"
        file_count = $wavFiles.Count
        files = $fileHashes
    }
}

# Write manifest
$results | ConvertTo-Json -Depth 10 | Out-File -FilePath $ManifestPath -Encoding UTF8

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Hash computation complete" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Manifest: $ManifestPath" -ForegroundColor Green
Write-Host ""
Write-Host "Please commit this file alongside the checkpoint to record" -ForegroundColor Yellow
Write-Host "the audio artifact integrity hashes." -ForegroundColor Yellow
