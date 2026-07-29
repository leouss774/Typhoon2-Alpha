# ============================================================
#  schedule_rates_update.ps1
#  Cree une tache planifiee Windows pour mettre a jour
#  les taux immobiliers depuis MeilleurTaux chaque mois.
#
#  Execution : Tous les 1er du mois a 03:00
#  Commande  : scripts\update_rates_scheduled.bat
# ============================================================
param(
    [string]$TaskName = "Typhoon-Rates-Update",
    [string]$ProjectPath = $null
)

# Determiner le chemin du projet
if (-not $ProjectPath) {
    $ProjectPath = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
}

Write-Host "========================================"
Write-Host "  Mise a jour planifiee des taux"
Write-Host "========================================"
Write-Host ""
Write-Host "  Tache        : $TaskName"
Write-Host "  Projet       : $ProjectPath"
Write-Host "  Frequence    : 1er de chaque mois a 03:00"
Write-Host ""

# Supprimer l'ancienne tache si elle existe
Write-Host "  Suppression de l'ancienne tache..." -NoNewline
& schtasks /Delete /TN $TaskName /F 2>$null | Out-Null
Write-Host " OK"

# Obtenir le chemin court (8.3) pour eviter les espaces dans le path
try {
    $fso = New-Object -ComObject Scripting.FileSystemObject
    $BatchPath = Join-Path $ProjectPath "scripts\update_rates_scheduled.bat"
    $ShortBatchPath = $fso.GetFile($BatchPath).ShortPath
    Write-Host "  Chemin court  : $ShortBatchPath"
} catch {
    Write-Host "  [WARN] Impossible d'obtenir le chemin court, utilisation du chemin long"
    $ShortBatchPath = "`"$BatchPath`""
}

# Creer la tache planifiee
Write-Host ""
Write-Host "  Creation de la tache planifiee..." -NoNewline

$Result = & schtasks /Create /SC MONTHLY /D 1 /TN $TaskName /TR "$ShortBatchPath" /ST 03:00 /F 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host " OK"
    Write-Host ""
    Write-Host "========================================"
    Write-Host "  Tache '$TaskName' creee avec succes !"
    Write-Host "========================================"
    Write-Host ""
    Write-Host "  Prochaine execution : 1er du mois a 03:00"
    Write-Host "  Commande           : $ShortBatchPath"
    Write-Host ""
    Write-Host "  Pour tester immediatement :"
    Write-Host "    Start-ScheduledTask -TaskName `"$TaskName`""
    Write-Host "    Get-Content `"$ProjectPath\backend\data\processed\rates_update.log`" -Tail 5"
    Write-Host ""
    Write-Host "  Pour verifier dans l'interface :"
    Write-Host "    Win+R -> taskschd.msc -> Bibliotheque -> $TaskName"
} else {
    Write-Host " ERREUR"
    Write-Host ""
    Write-Host "  $Result"
    Write-Host ""
    Write-Host "  Verifiez que vous avez les droits administrateur."
    Write-Host "  Ou creez la tache manuellement via taskschd.msc"
}
