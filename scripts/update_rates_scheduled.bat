@echo off
REM ============================================================
REM  Script de mise a jour des taux immobiliers
REM  (appele par le Task Scheduler chaque mois)
REM ============================================================

set PROJECT_DIR=%~dp0..\
set LOG_FILE=%PROJECT_DIR%backend\data\processed\rates_update.log

cd /d "%PROJECT_DIR%"

echo [%DATE% %TIME%] Debut mise a jour des taux >> "%LOG_FILE%"

python scripts\update_rates.py --update-env >> "%LOG_FILE%" 2>&1

echo [%DATE% %TIME%] Fin mise a jour des taux >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"
