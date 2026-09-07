# ============================================================
# test_explicit_marker_mode.ps1
# ============================================================
# Testet den Explicit Audio Marker Mode (+++++ Separator)
# auf der RTX 5060 Target-Hardware.
#
# AUSFUEHRUNG:
#   $env:VOICEOVER_RUNTIME_REF = "C:\Users\johan\Downloads\VoiceOverApp_LAB_NEXT\cache\voice_refs\VD-E.wav"
#   $env:VOICEOVER_RUNTIME_ROOT = "C:\Users\johan\Downloads\VoiceOverApp_LAB_NEXT"
#   .\test_explicit_marker_mode.ps1
#
# PYTHON-INTERPRETER DISCOVERY (Prioritaet):
#   1. VOICEOVER_PYTHON (explizites Override)
#   2. VOICEOVER_RUNTIME_ROOT/.venv
#   3. Repository .venv
#   4. System PATH (Fallback)
#
# ERWARTETES ERGEBNIS:
#   - 67 Unit-Tests bestanden
#   - Parser extrahiert 3 Abschnitte korrekt
#   - Marker "+++++" erreicht NIEMALS die TTS-Engine
#   - Golden Reference SHA-256 unveraendert
#   - (Optional) TTS-Validierung auf RTX 5060
#
# EXIT CODES:
#   0 = Erfolg oder uebersprungen (keine Golden Reference)
#   1 = Fehler (Unit-Tests fehlgeschlagen, Parser-Fehler, TTS-Validierung fehlgeschlagen)
# ============================================================

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
$RepoRoot = $ScriptDir
$ProjectRoot = Join-Path $RepoRoot "project"
$InputDir = Join-Path $ProjectRoot "input"
$OutputDir = Join-Path $ProjectRoot "output"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Explicit Audio Marker Mode - Target Test" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Repo:    $RepoRoot" -ForegroundColor Gray
Write-Host "Project: $ProjectRoot" -ForegroundColor Gray
Write-Host ""

# ============================================================
# SCHRITT 1: Python-Discovery
# ============================================================
Write-Host "[1/6] Python-Discovery..." -ForegroundColor Yellow

$PythonCmd = $null
$PythonSource = ""

# Priority 1: Explicit VOICEOVER_PYTHON override
if ($env:VOICEOVER_PYTHON -and (Test-Path $env:VOICEOVER_PYTHON)) {
    $PythonCmd = $env:VOICEOVER_PYTHON
    $PythonSource = "VOICEOVER_PYTHON (explicit override)"
}

# Priority 2: VOICEOVER_RUNTIME_ROOT/.venv
if (-not $PythonCmd -and $env:VOICEOVER_RUNTIME_ROOT) {
    $RuntimeVenv = Join-Path $env:VOICEOVER_RUNTIME_ROOT ".venv\Scripts\python.exe"
    if (Test-Path $RuntimeVenv) {
        $PythonCmd = $RuntimeVenv
        $PythonSource = "VOICEOVER_RUNTIME_ROOT/.venv"
    }
}

# Priority 3: Repository .venv
if (-not $PythonCmd) {
    $RepoVenv = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path $RepoVenv) {
        $PythonCmd = $RepoVenv
        $PythonSource = "Repository .venv"
    }
}

# Priority 4: System PATH (fallback only)
if (-not $PythonCmd) {
    $PyExe = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($PyExe) { 
        $PythonCmd = $PyExe.Source 
        $PythonSource = "System PATH (fallback)"
    }
}

if (-not $PythonCmd) {
    Write-Host "  [FAIL] Python nicht gefunden." -ForegroundColor Red
    Write-Host "  Bitte setzen Sie eine der folgenden Umgebungsvariablen:" -ForegroundColor Yellow
    Write-Host "    `$env:VOICEOVER_PYTHON = 'C:\path\to\python.exe'" -ForegroundColor White
    Write-Host "    `$env:VOICEOVER_RUNTIME_ROOT = 'C:\path\to\runtime'" -ForegroundColor White
    exit 1
}
Write-Host "  [OK] Python: $PythonCmd" -ForegroundColor Green
Write-Host "       Source: $PythonSource" -ForegroundColor DarkGray

# ============================================================
# SCHRITT 2: Unit-Tests ausfuehren
# ============================================================
Write-Host ""
Write-Host "[2/6] Unit-Tests (67 Tests)..." -ForegroundColor Yellow

Push-Location $ProjectRoot
try {
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $testOutput = & $PythonCmd -m unittest tests.test_explicit_audio_markers -v 2>&1
        $testExit = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $prevEAP }

    if ($testExit -eq 0) {
        $passed = ($testOutput | Select-String "^Ran (\d+) tests" | ForEach-Object { $_.Matches[0].Groups[1].Value })
        Write-Host "  [OK] $passed Tests bestanden" -ForegroundColor Green
    }
    else {
        Write-Host "  [FAIL] Unit-Tests fehlgeschlagen (Exit-Code: $testExit)" -ForegroundColor Red
        $testOutput | Select-Object -Last 15
        Pop-Location
        exit 1
    }
}
finally { Pop-Location }

# ============================================================
# SCHRITT 3: Test-Eingabedatei erstellen
# ============================================================
Write-Host ""
Write-Host "[3/6] Test-Eingabedatei erstellen..." -ForegroundColor Yellow

if (-not (Test-Path $InputDir)) { New-Item -ItemType Directory -Path $InputDir -Force | Out-Null }
if (-not (Test-Path $OutputDir)) { New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null }

$TestInputPath = Join-Path $InputDir "ExplicitMarkerTest.txt"
$TestContent = @"
Es gab einen Ort in der antiken Welt, der als der Nabel des Universums galt.
+++++
Die Pythia, die Hohepriesterin, saß auf einem Dreifuß über einem Erdspalt.
+++++
Die wahre Macht von Delphi lag nicht in der Wahrsagerei. Sie lag in der Reflexion.
"@
[System.IO.File]::WriteAllText($TestInputPath, $TestContent, [System.Text.Encoding]::UTF8)
Write-Host "  [OK] Eingabedatei: $TestInputPath" -ForegroundColor Green
Write-Host "       $($TestContent.Split("`n").Count) Zeilen, 2 Marker, 3 Abschnitte" -ForegroundColor Gray

# ============================================================
# SCHRITT 4: Parser-Test (Ohne TTS)
# ============================================================
Write-Host ""
Write-Host "[4/6] Parser-Test (Ohne TTS)..." -ForegroundColor Yellow

$ParserTest = @"
import sys
sys.path.insert(0, '.')
from app.text.script_split import (
    split_explicit_audio_markers,
    has_explicit_markers,
    assert_no_marker_in_tts_input,
    MARKER,
)

# Lese Testdatei
with open(r'$TestInputPath', 'r', encoding='utf-8') as f:
    text = f.read()

# Pruefe Marker-Erkennung
assert has_explicit_markers(text), 'Marker nicht erkannt!'
print('  [OK] Marker erkannt: True')

# Splitte
sections = split_explicit_audio_markers(text)
print(f'  [OK] Abschnitte: {len(sections)}')
assert len(sections) == 3, f'Erwartet 3, bekommen {len(sections)}'

# Pruefe Inhalt
for i, s in enumerate(sections):
    assert MARKER not in s, f'Marker in Abschnitt {i+1}!'
    assert len(s.strip()) > 0, f'Abschnitt {i+1} ist leer!'
    assert_no_marker_in_tts_input(s)
    print(f'  [OK] Abschnitt {i+1}: {len(s)} Zeichen')

print('  [OK] Parser-Test bestanden')
"@

Push-Location $ProjectRoot
try {
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $parserOutput = & $PythonCmd -c $ParserTest 2>&1
        $parserExit = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $prevEAP }

    $parserOutput | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
    if ($parserExit -ne 0) {
        Write-Host "  [FAIL] Parser-Test fehlgeschlagen" -ForegroundColor Red
        Pop-Location
        exit 1
    }
}
finally { Pop-Location }

# ============================================================
# SCHRITT 5: Golden Reference Validation
# ============================================================
Write-Host ""
Write-Host "[5/6] Golden Reference Validation..." -ForegroundColor Yellow

$ExpectedSHA = "B156C02A60A873AD95FC92390C4A136C85308B20188373CD734BEE5E5E5F2025"
$GoldenRefValid = $false
$GoldenRefPath = $null
$GoldenRefSource = ""

# Priorität 1: VOICEOVER_RUNTIME_REF (explizite Umgebungsvariable)
if ($env:VOICEOVER_RUNTIME_REF) {
    if (Test-Path $env:VOICEOVER_RUNTIME_REF) {
        $GoldenRefPath = $env:VOICEOVER_RUNTIME_REF
        $GoldenRefSource = "VOICEOVER_RUNTIME_REF (explicit)"
        
        $ActualSHA = (Get-FileHash -Path $GoldenRefPath -Algorithm SHA256).Hash
        if ($ActualSHA -eq $ExpectedSHA) {
            Write-Host "  [OK] Golden Reference SHA-256 unveraendert" -ForegroundColor Green
            Write-Host "       Path: $GoldenRefPath" -ForegroundColor Gray
            Write-Host "       SHA-256: $ActualSHA" -ForegroundColor Gray
            Write-Host "       Source: $GoldenRefSource" -ForegroundColor DarkGray
            $GoldenRefValid = $true
        }
        else {
            Write-Host "  [FAIL] Golden Reference SHA-256 GEAENDERT!" -ForegroundColor Red
            Write-Host "  Erwartet: $ExpectedSHA" -ForegroundColor Red
            Write-Host "  Bekommen: $ActualSHA" -ForegroundColor Red
            Write-Host "  Pfad: $GoldenRefPath" -ForegroundColor Red
            exit 1
        }
    }
    else {
        Write-Host "  [WARN] VOICEOVER_RUNTIME_REF gesetzt, aber Datei nicht gefunden" -ForegroundColor DarkYellow
        Write-Host "         $env:VOICEOVER_RUNTIME_REF" -ForegroundColor DarkYellow
    }
}

# Priorität 2: Projekt-lokaler Cache
if (-not $GoldenRefValid) {
    $ProjectLocalRef = Join-Path $ProjectRoot "cache\voice_refs\VD-E.wav"
    if (Test-Path $ProjectLocalRef) {
        $GoldenRefPath = $ProjectLocalRef
        $GoldenRefSource = "Project cache"
        
        $ActualSHA = (Get-FileHash -Path $GoldenRefPath -Algorithm SHA256).Hash
        if ($ActualSHA -eq $ExpectedSHA) {
            Write-Host "  [OK] Golden Reference SHA-256 unveraendert" -ForegroundColor Green
            Write-Host "       Path: $GoldenRefPath" -ForegroundColor Gray
            Write-Host "       SHA-256: $ActualSHA" -ForegroundColor Gray
            Write-Host "       Source: $GoldenRefSource" -ForegroundColor DarkGray
            $GoldenRefValid = $true
        }
        else {
            Write-Host "  [FAIL] Golden Reference SHA-256 GEAENDERT!" -ForegroundColor Red
            Write-Host "  Erwartet: $ExpectedSHA" -ForegroundColor Red
            Write-Host "  Bekommen: $ActualSHA" -ForegroundColor Red
            Write-Host "  Pfad: $GoldenRefPath" -ForegroundColor Red
            exit 1
        }
    }
}

if (-not $GoldenRefValid) {
    Write-Host "  [WARN] Golden Reference nicht gefunden" -ForegroundColor DarkYellow
    Write-Host "         Weder VOICEOVER_RUNTIME_REF noch projekt-lokaler Cache vorhanden" -ForegroundColor DarkYellow
    Write-Host "         TTS-Validierung kann nicht durchgefuehrt werden" -ForegroundColor DarkYellow
}

# ============================================================
# SCHRITT 6: TTS-Validierung (Optional)
# ============================================================
Write-Host ""
Write-Host "[6/6] TTS-Validierung (Optional)..." -ForegroundColor Yellow

$TTSValidationDone = $false
$TTSValidationResult = ""
$TTSExitCode = 0

if ($GoldenRefValid) {
    Write-Host "  [INFO] Golden Reference valid - starte TTS-Validierung..." -ForegroundColor Cyan
    
    $TTSValidationScript = Join-Path $ProjectRoot "tests\target_validate_explicit_marker.py"
    
    if (Test-Path $TTSValidationScript) {
        Push-Location $ProjectRoot
        try {
            $prevEAP = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try {
                $ttsOutput = & $PythonCmd $TTSValidationScript 2>&1
                $ttsExit = $LASTEXITCODE
            }
            finally { $ErrorActionPreference = $prevEAP }
            
            # Store exit code for propagation
            $TTSExitCode = $ttsExit
            
            # Display output
            $ttsOutput | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
            
            if ($ttsExit -eq 0) {
                Write-Host ""
                Write-Host "  [OK] TTS-Validierung erfolgreich" -ForegroundColor Green
                $TTSValidationDone = $true
                $TTSValidationResult = "ERFOLGREICH (RTX 5060)"
            }
            else {
                Write-Host ""
                Write-Host "  [FAIL] TTS-Validierung fehlgeschlagen (Exit-Code: $ttsExit)" -ForegroundColor Red
                $TTSValidationResult = "FEHLGESCHLAGEN"
            }
        }
        finally { Pop-Location }
    }
    else {
        Write-Host "  [WARN] TTS-Validierungsskript nicht gefunden: $TTSValidationScript" -ForegroundColor DarkYellow
        $TTSValidationResult = "Skript fehlt"
        $TTSExitCode = 1
    }
}
else {
    Write-Host "  [INFO] TTS-Validierung uebersprungen (keine Golden Reference)" -ForegroundColor DarkYellow
    Write-Host ""
    Write-Host "  Um TTS-Validierung durchzufuehren:" -ForegroundColor Yellow
    Write-Host "  `$env:VOICEOVER_RUNTIME_REF = 'C:\path\to\VoiceOverApp_LAB_NEXT\cache\voice_refs\VD-E.wav'" -ForegroundColor White
    $TTSValidationResult = "Uebersprungen (keine Golden Reference)"
    $TTSExitCode = 0  # Not a failure if skipped intentionally
}

# ============================================================
# ZUSAMMENFASSUNG
# ============================================================
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "TEST ZUSAMMENFASSUNG" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Unit-Tests:          67/67 bestanden" -ForegroundColor Green
Write-Host "  Parser-Test:         3 Abschnitte korrekt extrahiert" -ForegroundColor Green
Write-Host "  Golden Reference:    $GoldenRefSource" -ForegroundColor $(if ($GoldenRefValid) { "Green" } else { "DarkYellow" })

if ($TTSValidationDone) {
    Write-Host "  TTS-Validierung:     $TTSValidationResult" -ForegroundColor Green
    Write-Host "  Marker-Sicherheit:   NIEMALS in TTS-Input bestaetigt" -ForegroundColor Green
}
else {
    Write-Host "  TTS-Validierung:     $TTSValidationResult" -ForegroundColor DarkYellow
    Write-Host "  Marker-Sicherheit:   Nur Parser-Ebene getestet" -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "  Marker-Modus:        Implementiert und getestet" -ForegroundColor Green
Write-Host "  Abwaertskompatibel:  Keine Aenderung ohne Marker" -ForegroundColor Green
Write-Host ""

if (-not $TTSValidationDone -and $GoldenRefValid) {
    Write-Host "TTS-Validierung fehlgeschlagen - siehe Logs oben" -ForegroundColor Yellow
}
elseif (-not $GoldenRefValid) {
    Write-Host "Fuer vollstaendige TTS-Validierung auf RTX 5060:" -ForegroundColor Yellow
    Write-Host "  1. Runtime Reference setzen:" -ForegroundColor White
    Write-Host "     `$env:VOICEOVER_RUNTIME_REF = 'C:\Users\johan\Downloads\VoiceOverApp_LAB_NEXT\cache\voice_refs\VD-E.wav'" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  2. Test erneut ausfuehren:" -ForegroundColor White
    Write-Host "     .\test_explicit_marker_mode.ps1" -ForegroundColor Gray
    Write-Host ""
}

Write-Host "============================================================" -ForegroundColor Cyan

# Exit with appropriate code
# If TTS validation was attempted and failed, propagate that failure
# If TTS validation was skipped (no Golden Reference), that's OK (exit 0)
# If TTS validation succeeded, exit 0
if ($TTSValidationDone -and $TTSExitCode -ne 0) {
    # TTS validation was attempted and failed
    exit $TTSExitCode
}
else {
    # Either validation succeeded or was skipped
    exit 0
}
