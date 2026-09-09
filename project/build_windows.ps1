# ============================================================
#  VoiceOverApp 2.0 - Windows-Packaging (§7/§8/§9)
#
#  Baut eine echte Windows-Desktop-Anwendung:
#     dist\VoiceOverApp\VoiceOverApp.exe         (GUI, Doppelklick)
#     dist\VoiceOverApp\VoiceOverAppBackend.exe  (--job-Backend, Konsole)
#     dist\VoiceOverApp\_internal\               (Python + App-Code)
#
#  ONEDIR, Entry-Point = desktop.py (GUI-Hauptdatei).
#  ALLE Pfade relativ zum Anwendungsordner - keine
#  C:\Users\...-Hardcodierung; Ordner frei verschiebbar.
#
#  Build:  powershell -File build_windows.ps1
# ============================================================
param([switch]$SkipCopy)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "== VoiceOverApp.exe bauen (PyInstaller, Spec) ==" -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -m pip install --quiet pyinstaller pypdf windnd
if ($LASTEXITCODE -ne 0) { throw "Abhaengigkeiten fehlgeschlagen." }

& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean VoiceOverApp.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller-Build fehlgeschlagen." }

$Target = ".\dist\VoiceOverApp"
foreach ($exe in @("VoiceOverApp.exe", "VoiceOverAppBackend.exe")) {
    if (-not (Test-Path (Join-Path $Target $exe))) {
        throw "$exe wurde nicht gebaut - Spec pruefen."
    }
}

if (-not $SkipCopy) {
    Write-Host "== Externe Ressourcen (relativ) kopieren ==" -ForegroundColor Cyan
    foreach ($dir in @("models", "config", "voices", "pronunciation",
                       "input", "output", "cache", "logs", "benchmark",
                       "tools")) {
        if (Test-Path $dir) {
            robocopy $dir (Join-Path $target $dir) /E /NFL /NDL /NJH /NJS | Out-Null
        } else {
            New-Item -ItemType Directory -Force -Path (Join-Path $target $dir) | Out-Null
        }
    }
    foreach ($f in @("README.md", "LICENSES.md", "FINAL_APP_REPORT.md",
                     "FINAL_APP_MANIFEST.txt", "FINAL_VOICE_SETTINGS.txt",
                     "START_ANLEITUNG_KORREKTUR.md",
                     "install.ps1", "START.ps1", "START.bat",
                     "requirements.txt", "versions.json")) {
        if (Test-Path $f) { Copy-Item $f (Join-Path $target $f) -Force }
    }
}

Write-Host "== VD-E Identity-Lock Voraussetzung pruefen (§11) ==" -ForegroundColor Cyan
$prod = Get-Content .\config\production.json | ConvertFrom-Json
$ref = Join-Path $Target "cache\voice_refs\VD-E.wav"
if (Test-Path $ref) {
    $hash = (Get-FileHash $ref -Algorithm SHA256).Hash
    Write-Host ("VD-E SHA256 im Paket: " + $hash)
    if ($hash -ne $prod.reference_sha256) {
        Write-Host "WARNUNG: Hash weicht ab - App wird VD-E sperren (§24)." -ForegroundColor Yellow
    } else {
        Write-Host "VD-E Hash OK (Identity-Lock besteht im Paket)." -ForegroundColor Green
    }
} else {
    Write-Host ("Hinweis: VD-E.wav nicht im Build-Baum - beim ersten Start "
                + "aus der Produktion nach cache\voice_refs\ kopieren. "
                + "Erwarteter Hash: " + $prod.reference_sha256) -ForegroundColor Yellow
}

Write-Host "== Fertig: dist\VoiceOverApp\VoiceOverApp.exe ==" -ForegroundColor Green
Write-Host "Normalstart: Doppelklick auf VoiceOverApp.exe (GUI)."
Write-Host "CLI: VoiceOverAppBackend.exe --headless --files `"input.txt`" (bzw. exe --job)."
