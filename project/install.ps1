# ============================================================
#  VoiceOverApp - install.ps1
#  Prueft und installiert automatisch:
#    - Python 3.10-3.13 (winget, falls fehlt)
#    - Virtuelle Umgebung (.venv)
#    - PyTorch mit CUDA 12.8 (RTX 50xx/Blackwell-tauglich, cu128)
#      mit CPU-Fallback
#    - Python-Pakete (requirements.txt inkl. qwen-tts)
#    - FFmpeg (winget oder Download nach tools/)
#    - Qwen3-TTS-Modelle (Hugging Face, Apache-2.0)
#  Vorhandene Komponenten werden wiederverwendet.
#  Alles kostenlos, keine API-Keys, keine Abos.
# ============================================================
param(
    [switch]$SkipModels,
    [switch]$CpuOnly
)
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root
New-Item -ItemType Directory -Force -Path (Join-Path $Root "logs") | Out-Null
$InstallLog = Join-Path $Root "logs\install.log"

function Log([string]$msg, [string]$color = "Gray") {
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host $msg -ForegroundColor $color
    Add-Content -Path $InstallLog -Value "[$stamp] $msg" -Encoding UTF8
}

Log "=== VoiceOverApp Installation ===" "Cyan"

# ------------------------------------------------------------ 1) Python --
function Find-Python {
    $VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $VenvPython -PathType Leaf) { return $VenvPython }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        foreach ($v in @("3.12", "3.11", "3.13", "3.10")) {
            $test = & py "-$v" -c "import sys; print(sys.executable)" 2>$null
            if ($test -and -not $test.Contains("WindowsApps")) { return "py -$v" }
        }
    }
    foreach ($name in @("python3.12", "python3.11", "python3.13", "python", "python3")) {
        $g = Get-Command $name -ErrorAction SilentlyContinue
        if ($g -and $g.Source -and -not $g.Source.Contains("WindowsApps")) {
            return $name
        }
    }
    return $null
}

$Python = Find-Python
if (-not $Python) {
    Log "Kein Python 3.10-3.13 gefunden - installiere Python 3.12 via winget ..." "Yellow"
    try {
        winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements --silent | Out-Null
    } catch {
        Log "winget fehlgeschlagen ($_). Bitte Python 3.12 von python.org installieren und erneut starten." "Red"
        Read-Host "Enter zum Beenden"; exit 1
    }
    $found = Get-ChildItem (Join-Path $env:LOCALAPPDATA "Programs\Python") -Filter python.exe -Recurse -ErrorAction SilentlyContinue |
             Where-Object { $_.DirectoryName -match "Python312|Python311|Python313" } | Select-Object -First 1
    if ($found) { $Python = $found.FullName }
    if (-not $Python) {
        Log "Python wurde installiert, ist aber nicht im PFAD. Bitte dieses Fenster schliessen und START.bat erneut starten." "Yellow"
        Read-Host "Enter zum Beenden"; exit 1
    }
}
Log "Python: $Python" "Gray"

# ------------------------------------------------- 2) Virtuelle Umgebung --
$VenvDir = Join-Path $Root ".venv"
$Vpy = Join-Path $VenvDir "Scripts\python.exe"
$Requirements = Join-Path $Root "requirements.txt"

if (-not (Test-Path -LiteralPath $Vpy -PathType Leaf)) {
    Log "Erstelle virtuelle Umgebung .venv ..." "Yellow"
    if ($Python -like "py *") {
        $parts = $Python.Split(" ")
        $exe = $parts[0]
        $arg = $parts[1]
        & $exe $arg -m venv $VenvDir
    } else {
        & $Python -m venv $VenvDir
    }
    if ($LASTEXITCODE -ne 0) {
        Log "venv-Erstellung fehlgeschlagen (Exit $LASTEXITCODE)." "Red"
        Read-Host "Enter zum Beenden"; exit 1
    }
    if (-not (Test-Path -LiteralPath $Vpy -PathType Leaf)) {
        Log "venv konnte nicht erstellt werden - $Vpy fehlt." "Red"
        Read-Host "Enter zum Beenden"; exit 1
    }
}
if (-not (Test-Path -LiteralPath $Vpy -PathType Leaf)) {
    Log "Python runtime missing: $Vpy" "Red"
    throw "Python runtime missing: $Vpy"
}
Log "Venv Python: $Vpy" "Gray"

# pip aktualisieren -- korrekt: $Vpy ist nur die Executable, Argumente getrennt
Log "pip aktualisieren ..." "Gray"
& $Vpy -m pip install --upgrade pip --quiet
if ($LASTEXITCODE -ne 0) {
    Log "pip-Upgrade fehlgeschlagen (Exit $LASTEXITCODE)." "Red"
    throw "pip upgrade failed with exit code $LASTEXITCODE"
}

# ------------------------------------------------------- 3) PyTorch/CUDA --
$needTorch = $true
try {
    $hasTorch = & $Vpy -c "import torch; print(torch.__version__)" 2>$null
    if ($hasTorch) {
        $needTorch = $false
        Log "PyTorch bereits installiert: $hasTorch" "Gray"
    }
} catch {}

function Has-NvidiaGPU {
    try {
        nvidia-smi 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

if ($needTorch) {
    $gpu = Has-NvidiaGPU
    if ($gpu -and -not $CpuOnly) {
        Log "Installiere PyTorch mit CUDA 12.8 (cu128) - Download ca. 3 GB, einmalig ..." "Yellow"
        & $Vpy -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128 --quiet
        if ($LASTEXITCODE -ne 0) {
            Log "CUDA-Installation fehlgeschlagen (Exit $LASTEXITCODE) - weiche auf CPU-Version aus." "Yellow"
            & $Vpy -m pip install torch torchaudio --quiet
            if ($LASTEXITCODE -ne 0) {
                Log "PyTorch CPU-Installation fehlgeschlagen (Exit $LASTEXITCODE)." "Red"
                throw "PyTorch install failed with exit code $LASTEXITCODE"
            }
        }
    } else {
        Log "Keine NVIDIA-GPU erkannt (oder -CpuOnly) - installiere CPU-PyTorch ..." "Yellow"
        & $Vpy -m pip install torch torchaudio --quiet
        if ($LASTEXITCODE -ne 0) {
            Log "PyTorch CPU-Installation fehlgeschlagen (Exit $LASTEXITCODE)." "Red"
            throw "PyTorch install failed with exit code $LASTEXITCODE"
        }
    }
}
# Pruefe PyTorch aktiv -- nur melden wenn wirklich vorhanden
try {
    $codeTorch = 'import torch; print(torch.__version__ + " cuda=" + str(torch.cuda.is_available()) + " cudaver=" + str(torch.version.cuda))'
    $t = & $Vpy -c $codeTorch 2>$null
    if ($t) { Log "PyTorch aktiv: $t" "Gray" }
    else { Log "PyTorch Pruefung: keine Ausgabe (Installation evtl. fehlgeschlagen)." "Yellow" }
} catch {
    Log "PyTorch Pruefung fehlgeschlagen: $_" "Yellow"
}

# --------------------------------------------------- 4) Pakete (app) ----
Log "Installiere Python-Pakete (qwen-tts, transformers 4.57.3, ...) ..." "Yellow"
if (-not (Test-Path -LiteralPath $Requirements -PathType Leaf)) {
    Log "requirements.txt nicht gefunden: $Requirements" "Red"
    throw "requirements.txt missing: $Requirements"
}
& $Vpy -m pip install -r $Requirements --quiet
if ($LASTEXITCODE -ne 0) {
    Log "Paketinstallation fehlgeschlagen (Exit $LASTEXITCODE) - Details:" "Red"
    & $Vpy -m pip install -r $Requirements
    Log "Bitte Fehler oben pruefen und erneut ausfuehren." "Red"
    Read-Host "Enter zum Beenden"; exit 1
}

# ------------------------------------------------------------ 5) FFmpeg --
$ff = Get-Command ffmpeg -ErrorAction SilentlyContinue
$ffLocalPath = Join-Path $Root "tools\ffmpeg\ffmpeg.exe"
$ffLocal = Test-Path -LiteralPath $ffLocalPath -PathType Leaf
if (-not $ff -and -not $ffLocal) {
    Log "FFmpeg fehlt - versuche winget ..." "Yellow"
    try {
        winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements --silent | Out-Null
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    } catch { Log "winget-FFmpeg fehlgeschlagen ($_) " "Yellow" }
    $ff = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if (-not $ff) {
        Log "Lade FFmpeg direkt nach tools\ffmpeg ..." "Yellow"
        try {
            New-Item -ItemType Directory -Force -Path (Join-Path $Root "tools") | Out-Null
            $zip = Join-Path $env:TEMP "ffmpeg.zip"
            $ffDir = Join-Path $Root "tools\_ff"
            Invoke-WebRequest -Uri "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile $zip -UseBasicParsing
            Expand-Archive -Path $zip -DestinationPath $ffDir -Force
            $exe = Get-ChildItem $ffDir -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
            New-Item -ItemType Directory -Force -Path (Join-Path $Root "tools\ffmpeg") | Out-Null
            Move-Item -LiteralPath $exe.FullName -Destination $ffLocalPath -Force
            Remove-Item -LiteralPath $ffDir -Recurse -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
        } catch { Log "FFmpeg-Download fehlgeschlagen ($_). MP3-Ausgabe deaktiviert (WAV funktioniert)." "Yellow" }
    }
}

# ------------------------------------------------------ 6) Modelle ------
if (-not $SkipModels) {
    Log "Lade Qwen3-TTS-Modelle (1.7B CustomVoice + Tokenizer, ca. 4 GB) ..." "Yellow"
    Log "(Fortschritt siehe Konsole; Abbruch jederzeit mit Strg+C, Resume beim naechsten Lauf)" "Gray"
    $appMain = Join-Path $Root "app\main.py"
    & $Vpy $appMain --download-models
    if ($LASTEXITCODE -ne 0) {
        Log "Modell-Download fehlgeschlagen - Internetverbindung pruefen und erneut starten. (Exit $LASTEXITCODE)" "Red"
    }
}

# ------------------------------------------------ 7) Abschluss-Checks --
Log "Schreibe versions.json + environment.json ..." "Gray"
try {
    $appMain = Join-Path $Root "app\main.py"
    & $Vpy $appMain --info | Add-Content -Path $InstallLog -Encoding UTF8
} catch {}
try {
    $codeVer = 'import json,torch,transformers,platform,datetime; d={"created":datetime.datetime.now().isoformat(),"python":platform.python_version(),"torch":torch.__version__,"torch_cuda":torch.version.cuda,"transformers":transformers.__version__,"app":"1.0.0"}; json.dump(d,open("versions.json","w"),indent=2)'
    & $Vpy -c $codeVer
    if ($LASTEXITCODE -ne 0) { Log "versions.json Schreiben fehlgeschlagen (Exit $LASTEXITCODE)." "Yellow" }
} catch { Log "versions.json Fehler: $_" "Yellow" }

New-Item -ItemType File -Path (Join-Path $Root ".installed") -Force | Out-Null
Log "=== Installation abgeschlossen ===" "Green"
Log "Start: Doppelklick auf START.bat" "Green"
# Kein automatischer Read-Host in Headless-Aufruf; nur interaktiv warten wenn Konsole vorhanden
if ($Host.Name -match "ConsoleHost") { Read-Host "Enter zum Beenden" | Out-Null }
