$taskName = 'MiniCreche-Backend'

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Tâche '$taskName' supprimée."
} else {
    Write-Host "Aucune tâche '$taskName' à supprimer."
}
