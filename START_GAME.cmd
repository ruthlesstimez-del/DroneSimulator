@echo off
cd /d "%~dp0"
echo Starting Drone Duel...
echo You control PlayerDrone. The AI follows using simulated radar.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_duel.ps1"
if errorlevel 1 (
    echo.
    echo Game startup failed. See duel_artifacts\error.log.
    pause
)
