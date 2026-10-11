[CmdletBinding()]
param(
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [string]$TaskName = 'Runr Local Automation'
)

$ErrorActionPreference = 'Stop'
$controller = Join-Path $RepositoryRoot '.venv\Scripts\runr-auto.exe'
if (-not (Test-Path -LiteralPath $controller -PathType Leaf)) {
    throw "Controller is not installed at $controller. Run: .venv\Scripts\python.exe -m pip install -e .\runr_automation"
}

$arguments = "--repo-root `"$RepositoryRoot`" daemon"
$action = New-ScheduledTaskAction -Execute $controller -Argument $arguments -WorkingDirectory $RepositoryRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 2) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description 'Local Linear-driven Runr engineering controller' -Force | Out-Null
Write-Output "Installed per-user task '$TaskName'."
