<#
.SYNOPSIS
    Planifie la mise a jour automatique de la base DVF (tous les 6 mois).

.DESCRIPTION
    Cree une tache planifiee Windows qui execute update_dvf.py
    le 15 avril et le 15 octobre a 3h00, en synchronisation avec
    les publications semestrielles de la DGFiP.

    Usage :
      powershell -ExecutionPolicy Bypass -File scripts\schedule_dvf_update.ps1

    Verification :
      Start-ScheduledTask -TaskName "Typhoon-DVF-Update"
      Get-ScheduledTask -TaskName "Typhoon-DVF-Update" | Format-List
#>

param(
    [string]$ProjectPath = (Split-Path -Parent (Split-Path -Parent $PSCommandPath)),
    [string]$TaskName = "Typhoon-DVF-Update"
)

# --- Verifications ---
if (-not (Test-Path "$ProjectPath\scripts\update_dvf.py")) {
    Write-Host "ERREUR: update_dvf.py introuvable dans $ProjectPath\scripts\" -ForegroundColor Red
    exit 1
}

# --- Log ---
$LogDir = "$ProjectPath\backend\data\processed"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$LogFile = "$LogDir\dvf_update.log"

# --- Commande a executer ---
$BatchPath = "$ProjectPath\scripts\update_dvf_scheduled.bat"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  CREATION DE LA TACHE PLANIFIEE DVF" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Projet :    $ProjectPath"
Write-Host "  Tache :     $TaskName"
Write-Host "  Calendrier : 15 avril et 15 octobre (3h00)"
Write-Host "  Script :    $BatchPath"
Write-Host "  Logs :      $LogFile"
Write-Host ""

# --- Supprimer l'ancienne tache si elle existe ---
& schtasks /Delete /TN $TaskName /F 2>$null | Out-Null

# --- Obtenir le chemin court (8.3) pour eviter les espaces ---
$ShortBatchPath = (New-Object -ComObject Scripting.FileSystemObject).GetFile("$BatchPath").ShortPath
Write-Host "  Chemin court : $ShortBatchPath"
Write-Host ""

# --- Creer la nouvelle tache ---
$Result = & schtasks /Create /SC MONTHLY /D 15 /M APR,OCT /TN $TaskName /TR "$ShortBatchPath" /ST 03:00 /F 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Tache '$TaskName' creee avec succes !" -ForegroundColor Green
} else {
    Write-Host "  [ERREUR] $Result" -ForegroundColor Red
    Write-Host ""
    Write-Host "Note : Si vous n'etes pas administrateur, la tache sera creee"
    Write-Host "mais ne s'executera que lorsque vous serez connecte."
}

Write-Host ""
Write-Host "--------------------------------------------------" -ForegroundColor Cyan
Write-Host "  POUR VERIFIER LA TACHE :" -ForegroundColor Yellow
Write-Host "--------------------------------------------------" -ForegroundColor Cyan
Write-Host "  1. Win+r -> taskschd.msc -> Bibliotheque -> $TaskName"
Write-Host "  2. Ou : Get-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
Write-Host ""
Write-Host "  POUR TESTER IMMEDIATEMENT :" -ForegroundColor Yellow
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
Write-Host "  Get-Content '$LogFile' -Tail 5" -ForegroundColor White
Write-Host ""
Write-Host "[OK] Termine !" -ForegroundColor Green
Write-Host ""
