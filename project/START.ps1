# ============================================================
#  VoiceOverApp 2.0 - START.ps1 (ENTWICKLERSTART)
#
#  Standard (kein Parameter):  startet die DESKTOP-GUI
#                              (Tkinter, Entry-Point desktop.py).
#                              Kein Browser, kein Webserver,
#                              kein Port 8750.
#
#  Optionale Entwickler-Modi:
#     .\START.ps1 -Headless -Files "input\text.txt"   CLI-Pipeline
#     .\START.ps1 -Cli "--info"                       beliebiger CLI-Aufruf
#     .\START.ps1 -WebServer                          alter Webserver
#                                                      (nur explizit!)
#
#  Alle Pfade relativ zum Ordner dieser Datei (App-Root).
# ============================================================
param(
    [switch]$Headless,
    [string[]]$Files,
    [string]$Cli = "",
    [switch]$WebServer
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

# --- Python der virtuellen Umgebung (relativ, kein Benutzerpfad) ---
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "== Ersteinrichtung: install.ps1 wird gestartet ==" -ForegroundColor Cyan
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "install.ps1")
    if (-not (Test-Path $VenvPython)) {
        Write-Host "Installation fehlgeschlagen. Bitte logs\install.log pruefen." -ForegroundColor Red
        Read-Host "Enter zum Beenden"
        exit 1
    }
}
if (-not (Test-Path (Join-Path $Root ".installed"))) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "install.ps1")
}

$MainPy = Join-Path $Root "app\main.py"

# --- Modus-Auswahl ---------------------------------------------------
if ($WebServer) {
    # Expliziter Entwickler-Webserver (bewusst NICHT Standard)
    & $VenvPython $MainPy --webserver
    exit $LASTEXITCODE
}
if ($Headless) {
    $pyArgs = @($MainPy, "--headless")
    if ($Files) { $pyArgs += "--files"; $pyArgs += $Files }
    & $VenvPython @pyArgs
    exit $LASTEXITCODE
}
if ($Cli) {
    & $VenvPython $MainPy $Cli
    exit $LASTEXITCODE
}

# --- Standard: DESKTOP-GUI -------------------------------------------
Write-Host "  VoiceOverApp Desktop-GUI wird gestartet ..." -ForegroundColor Green
& $VenvPython (Join-Path $Root "desktop.py")
exit $LASTEXITCODE
