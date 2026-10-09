param(
    [string]$WorkspaceId = "",
    [string]$PythonPath = ".\.venv\Scripts\python.exe",
    [string]$ProjectDir = $PSScriptRoot,
    [string]$DataDir = ".backend_data",
    [ValidateSet("sqlite", "file")]
    [string]$Storage = "sqlite",
    [string]$OverrideJson = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $WorkspaceId) {
    Write-Host "ERROR: -WorkspaceId is required."
    exit 1
}

Set-Location $ProjectDir

$logsDir = Join-Path $ProjectDir "logs"
if (-not (Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir | Out-Null
}

$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$logFile = Join-Path $logsDir "workspace_run_$timestamp.log"

Write-Host "Running workspace through unified backend..."
Write-Host "ProjectDir: $ProjectDir"
Write-Host "WorkspaceId: $WorkspaceId"
Write-Host "PythonPath: $PythonPath"
Write-Host "Storage: $Storage"
Write-Host "DataDir: $DataDir"
Write-Host "Log: $logFile"

$cmd = @(
    $PythonPath,
    "workspace_runner.py",
    "--data-dir", $DataDir,
    "--storage", $Storage,
    "run",
    "--workspace", $WorkspaceId
)

if ($OverrideJson) {
    $cmd += @("--override-json", $OverrideJson)
}

& $cmd 2>&1 | Tee-Object -FilePath $logFile
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    Write-Host "Workspace run failed with exit code $exitCode"
    exit $exitCode
}

Write-Host "Workspace run completed successfully."
exit 0
