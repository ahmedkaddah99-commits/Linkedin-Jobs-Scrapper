param(
    [string]$PythonPath = ".\.venv\Scripts\python.exe",
    [string]$ProjectDir = $PSScriptRoot,
    [string]$ExcelMode = "new-sheet"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $ProjectDir

$logsDir = Join-Path $ProjectDir "logs"
if (-not (Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir | Out-Null
}

$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$logFile = Join-Path $logsDir "pipeline_$timestamp.log"

Write-Host "Running daily pipeline..."
Write-Host "ProjectDir: $ProjectDir"
Write-Host "PythonPath: $PythonPath"
Write-Host "ExcelMode: $ExcelMode"
Write-Host "Log: $logFile"

& $PythonPath orchestrator.py --stage4-excel-mode $ExcelMode 2>&1 | Tee-Object -FilePath $logFile
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    Write-Host "Pipeline failed with exit code $exitCode"
    exit $exitCode
}

Write-Host "Pipeline completed successfully."
exit 0
