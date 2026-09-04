@echo off
rem ============================================================
rem  VoiceOverApp 2.0 - NORMALER START
rem  Doppelklick = echte Desktop-GUI (Tkinter). Kein Browser,
rem  kein Webserver, kein Port 8750.
rem  Alle Pfade relativ zum Ordner dieser Datei (App-Root).
rem ============================================================
setlocal
cd /d "%~dp0"
title VoiceOverApp

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo Ersteinrichtung: install.ps1 wird gestartet ...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
)
if not exist "%PY%" (
    echo Installation fehlgeschlagen. Bitte logs\install.log pruefen.
    pause
    exit /b 1
)

if not exist "%~dp0.installed" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
)

rem --- Desktop-GUI starten (Entry-Point: desktop.py) ---------------
"%PY%" "%~dp0desktop.py" %*
if errorlevel 1 (
    echo.
    echo VoiceOverApp wurde mit einem Fehler beendet - siehe logs\.
    pause
)
endlocal
