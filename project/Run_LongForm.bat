@echo off
rem ============================================================
rem  Long-Form Baseline – produces project/reproduction/longform/*
rem  for the 7 selected voices. Requires finished RTX 5060 setup
rem  (install.ps1 already executed, qwen-tts+torch in .venv).
rem  Does NOT run VoiceDesign unless reference WAV is missing.
rem ============================================================
chcp 65001 >nul 2>&1
setlocal
cd /d "%~dp0"
title VoiceOverApp – Long-Form Baseline

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo Ersteinrichtung noetig: install.ps1 wird gestartet ...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
)
if not exist "%PY%" (
    echo Python-Umgebung fehlt. Bitte install.ps1 pruefen.
    pause
    exit /b 1
)

echo.
echo === Long-Form Baseline (7 voices) ===
echo Starte aus: %CD%
echo Ergebnisse unter: reproduction\longform\
echo.
"%PY%" "%~dp0tools\longform_benchmark.py" %*
set RC=%ERRORLEVEL%
echo.
echo === Fertig (ExitCode %RC%) ===
pause
endlocal
exit /b %RC%
