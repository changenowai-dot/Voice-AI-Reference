@echo off
rem ============================================================
rem  VoiceOverApp - Desktop-GUI starten (Quellmodus)
rem  Bevorzugt .venv, sonst install.ps1 ausfuehren.
rem ============================================================
setlocal
cd /d "%~dp0"
title VoiceOverApp

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo Keine virtuelle Umgebung gefunden - Installation wird gestartet ...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
)
if not exist "%PY%" (
    echo Installation fehlgeschlagen. Bitte logs\install.log pruefen.
    pause
    exit /b 1
)
"%PY%" "%~dp0desktop.py" %*
if errorlevel 1 pause
endlocal
