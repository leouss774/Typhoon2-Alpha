# ============================================================
# Installation de l'orchestrateur Typhoon avec TOUT sous D:
# (venv Python, cache pip, fichiers temporaires, config Copernicus,
# cache Copernicus/DVF) - rien n'est ecrit sur C:.
#
# A lancer depuis PowerShell, dans le dossier backend/ :
#   cd D:\Talan\Typhoon-2\backend
#   powershell -ExecutionPolicy Bypass -File .\setup_windows_d_drive.ps1
#
# Pourquoi ce script : par defaut, Windows installe les paquets Python et
# les fichiers temporaires sous C:\Users\<vous>\... meme si votre projet
# est sur D:, et cdsapi lit sa config depuis C:\Users\<vous>\.cdsapirc par
# defaut. Ce script force tout (venv, cache pip, TEMP/TMP, config
# Copernicus) a rester sous D:\Talan\Typhoon-2.
# ============================================================

$ErrorActionPreference = "Stop"

$ProjectRoot = "D:\Talan\Typhoon-2\backend"
$PipCacheDir = "D:\Talan\Typhoon-2\.pip-cache"
$TempDir     = "D:\Talan\Typhoon-2\.tmp"

Write-Host "Dossier projet    : $ProjectRoot"
Write-Host "Cache pip         : $PipCacheDir"
Write-Host "Fichiers temp.    : $TempDir"
Write-Host ""

New-Item -ItemType Directory -Force -Path $PipCacheDir | Out-Null
New-Item -ItemType Directory -Force -Path $TempDir | Out-Null

Set-Location $ProjectRoot

# Redirige les fichiers temporaires (utilises par pip, xarray, et par
# cdsapi pendant le telechargement) vers D: pour cette session PowerShell.
$env:TEMP = $TempDir
$env:TMP = $TempDir
$env:PIP_CACHE_DIR = $PipCacheDir

# Config Copernicus (CDS) passee par variables d'environnement plutot que
# par le fichier C:\Users\<vous>\.cdsapirc : cdsapi lit ces deux variables
# en priorite (voir cdsapi/api.py, fonction get_url_key_verify), donc rien
# n'est ecrit sur C: pour ca non plus.
$env:CDSAPI_URL = "https://cds.climate.copernicus.eu/api"
$env:CDSAPI_KEY = "be100142-59b8-4e65-a3ad-f8525d1ce180"

Write-Host "Creation du venv sous $ProjectRoot\.venv ..."
python -m venv .venv

Write-Host "Activation du venv..."
& .\.venv\Scripts\Activate.ps1

Write-Host "Installation des dependances (cache pip force sous D:)..."
pip install --cache-dir $PipCacheDir -r requirements.txt

Write-Host ""
Write-Host "Termine. Tout est installe/telecharge sous D:\Talan\Typhoon-2, rien sur C: :"
Write-Host "  - venv Python       : $ProjectRoot\.venv"
Write-Host "  - cache pip         : $PipCacheDir"
Write-Host "  - fichiers temp.    : $TempDir"
Write-Host "  - config Copernicus : variables d'environnement (pas de fichier sur C:)"
Write-Host "  - cache Copernicus  : $ProjectRoot\data\lookup\copernicus (auto)"
Write-Host "  - lookup DVF        : $ProjectRoot\data\lookup\dvf (auto)"
Write-Host ""
Write-Host "IMPORTANT : dans toute NOUVELLE fenetre PowerShell (pour relancer le CLI"
Write-Host "plus tard), il faut redefinir ces variables avant de lancer python -m app.cli,"
Write-Host "sinon Windows retombe sur ses dossiers habituels sur C: :"
Write-Host '  $env:TEMP = "D:\Talan\Typhoon-2\.tmp"'
Write-Host '  $env:TMP = "D:\Talan\Typhoon-2\.tmp"'
Write-Host '  $env:CDSAPI_URL = "https://cds.climate.copernicus.eu/api"'
Write-Host '  $env:CDSAPI_KEY = "be100142-59b8-4e65-a3ad-f8525d1ce180"'
Write-Host ""
Write-Host "Pensez a activer le venv aussi dans ces nouvelles fenetres :"
Write-Host '  cd D:\Talan\Typhoon-2\backend'
Write-Host '  .\.venv\Scripts\Activate.ps1'
