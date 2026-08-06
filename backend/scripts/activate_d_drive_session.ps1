# A relancer (via "." pour que les variables restent actives dans votre
# session PowerShell courante) a chaque nouvelle fenetre PowerShell avant
# d'utiliser python -m app.cli, pour garder tout sous D: :
#
#   cd D:\Talan\Typhoon-2\backend
#   . .\activate_d_drive_session.ps1
#
# (executer setup_windows_d_drive.ps1 une seule fois avant, pour creer le
# venv et installer les dependances)

$env:TEMP = "D:\Talan\Typhoon-2\.tmp"
$env:TMP = "D:\Talan\Typhoon-2\.tmp"
$env:PIP_CACHE_DIR = "D:\Talan\Typhoon-2\.pip-cache"
$env:CDSAPI_URL = "https://cds.climate.copernicus.eu/api"
$env:CDSAPI_KEY = "be100142-59b8-4e65-a3ad-f8525d1ce180"

Set-Location "D:\Talan\Typhoon-2\backend"
& .\.venv\Scripts\Activate.ps1

Write-Host "Session prete : venv actif, TEMP/pip/Copernicus sous D:."
