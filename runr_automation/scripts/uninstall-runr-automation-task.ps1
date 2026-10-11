[CmdletBinding()]
param([string]$TaskName = 'Runr Local Automation')

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $task) {
    Write-Output "Task '$TaskName' is not installed."
    exit 0
}
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Output "Removed task '$TaskName'. Runtime data was preserved."
