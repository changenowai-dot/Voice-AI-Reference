@echo off
rem ============================================================
rem  Long-Form BASELINE – 7 Shortlist-Stimmen.
rem  Startet die komplette 7-Voice-Baseline. Der Segment-Cache
rem  wird (wie bisher) fuer Wiederverwendung herangezogen, damit
rem  bestehende reproduzierte Ergebnisse konsistent bleiben.
rem  Fuer den echten Top-3-Long-Form-Lauf bitte stattdessen
rem  Run_TOP3_LongForm.bat verwenden.
rem ============================================================
chcp 65001 >nul 2>&1
setlocal
cd /d "%~dp0"
title VoiceOverApp – Long-Form Baseline (7 voices)

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
echo Ergebnisse: reproduction\longform\
echo.
"%PY%" "%~dp0tools\longform_benchmark.py" %*
set RC=%ERRORLEVEL%
echo.
echo === Fertig (ExitCode %RC%) ===
echo Ergebnisse unter: reproduction\longform\SUMMARY.md
pause
endlocal
exit /b %RC%
