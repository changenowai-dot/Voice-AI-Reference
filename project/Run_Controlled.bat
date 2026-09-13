@echo off
rem ============================================================
rem  CONTROLLED SHORT RUN – ca. 4–5 echte Segmente mit der
rem  Problemstimme de_female_warm_empathetic_01 über die UNVER-
rem  ÄNDERTE Produktions-Pipeline (Segmentierung/QC/Final-Gate/
rem  Retry) mit ECHTER Neusynthese (cache_enabled=False).
rem
rem  Ziel: vor dem vollen Top-3-Long-Form belegen, dass die
rem  0.16s-/Silence-Wiederholungen verschwunden sind.
rem
rem  Ausgabe: project\reproduction\CONTROLLED_SHORT\<vid>\
rem ============================================================
chcp 65001 >nul 2>&1
setlocal
cd /d "%~dp0"
title VoiceOverApp – Controlled Short Run
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo .venv fehlt – bitte erst install.ps1 ausfuehren.
    pause
    exit /b 1
)
echo.
echo === Controlled Short Run (de_female_warm_empathetic_01) ===
echo Starte aus: %CD%
echo.
"%PY%" "%~dp0tools\controlled_short_run.py" %*
set RC=%ERRORLEVEL%
echo.
echo === Ende (ExitCode %RC%) ===
echo Ergebnisse: reproduction\CONTROLLED_SHORT\de_female_warm_empathetic_01\
pause
endlocal
exit /b %RC%
