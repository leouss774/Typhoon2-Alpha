@echo off
REM ============================================================
REM  Script de mise a jour DVF (appele par le Task Scheduler)
REM  Cree automatiquement par scripts/schedule_dvf_update.ps1
REM ============================================================

REM Chemin absolu vers la racine du projet (ajuster si deplace)
set PROJECT_DIR=%~dp0..\
set LOG_FILE=%PROJECT_DIR%backend\data\processed\dvf_update.log

REM Se placer dans le dossier du projet
cd /d "%PROJECT_DIR%"

REM Date/heure de debut
echo [%DATE% %TIME%] Debut de la mise a jour DVF >> "%LOG_FILE%"

REM Executer le script Python
python scripts\update_dvf.py >> "%LOG_FILE%" 2>&1

REM Date/heure de fin
echo [%DATE% %TIME%] Fin de la mise a jour DVF >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"
