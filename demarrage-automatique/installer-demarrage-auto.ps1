# Creates a task for the currently logged-in Windows user. No administrator
# account, password, or WireGuard private key is stored in the task.
$ErrorActionPreference = 'Stop'

$taskName = 'MiniCreche-Backend'
$scriptPath = Join-Path $PSScriptRoot 'demarrer-backend.bat'

if (-not (Test-Path $scriptPath)) {
    throw "Script introuvable : $scriptPath"
}

$action = New-ScheduledTaskAction -Execute $env:ComSpec -Argument "/c `"$scriptPath`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
Write-Host "Tâche '$taskName' créée : le serveur Mini Crèche démarrera à la prochaine ouverture de session."
Write-Host "Pour tester maintenant, double-cliquez sur demarrer-backend.bat."
