@echo off
rem ============================================================
rem  TOP-3 LONG-FORM REAL RUN
rem  ----------------------------------------------------------
rem  Echter Testlauf ueber die drei vom Benutzer ausgewaehlten
rem  Stimmen mit deaktiviertem Segment-Cache (jedes Segment wird
rem  neu synthetisiert). Referenz-WAVs / VoiceClone-Prompts
rem  werden wiederverwendet.
rem
rem  Stimmen:
rem     1. de_female_warm_empathetic_01       (persoenl. Favorit)
rem     2. de_female_deep_warm_documentary_01
rem     3. en_male_warm_grounded_humanist_01
rem
rem  Ausgabe: project\reproduction\TOP3_LONGFORM_REAL\
rem  Die 7-Voice-Baseline unter reproduction\longform\ wird
rem  NICHT ueberschrieben.
rem ============================================================
chcp 65001 >nul 2>&1
setlocal
cd /d "%~dp0"
title VoiceOverApp – TOP-3 Long-Form (Real)

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
echo === TOP-3 Long-Form REAL RUN (segment-cache: AUS) ===
echo Stimmen:
echo   - de_female_warm_empathetic_01
echo   - de_female_deep_warm_documentary_01
echo   - en_male_warm_grounded_humanist_01
echo Ausgabe: reproduction\TOP3_LONGFORM_REAL\
echo Starte aus: %CD%
echo.
"%PY%" "%~dp0tools\longform_benchmark.py" --top3 --fresh %*
set RC=%ERRORLEVEL%
echo.
if %RC%==0 (
    echo === OK – echte Neusynthese abgeschlossen (ExitCode 0) ===
) else if %RC%==2 (
    echo === WARNUNG – Cache-Reuse erkannt, KEINE saubere Neusynthese! ===
) else (
    echo === FEHLER (ExitCode %RC%) ===
)
echo Ergebnisse unter: reproduction\TOP3_LONGFORM_REAL\SUMMARY.md
pause
endlocal
exit /b %RC%
