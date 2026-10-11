$ErrorActionPreference = 'Stop'
$repository = Split-Path $PSScriptRoot -Parent
$python = Join-Path $repository '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Project virtual environment missing' }
$version = & $python --version
if ($version -ne 'Python 3.12.7') { throw "Unsupported interpreter: $version" }
$destination = Join-Path $env:USERPROFILE 'Runr-Historical-Archives\backups'
New-Item -ItemType Directory -Path $destination -Force | Out-Null
$manifestPath = Join-Path $destination 'download-manifest.json'
# Credentials remain on the VPS. Signed links are stored locally, outside Git.
$manifest = & ssh -o BatchMode=yes -o ConnectTimeout=20 runr-vps 'sudo systemd-run --quiet --wait --pipe --collect -p EnvironmentFile=/etc/runr/customer-candidate-20261010/api.env -p EnvironmentFile=/etc/runr/connections-release.env /opt/runr/.venv/bin/python /opt/runr-ops/list-device-backup-objects.py'
if ($LASTEXITCODE -ne 0) { throw 'Cannot obtain backup inventory; existing copies preserved' }
[IO.File]::WriteAllText($manifestPath, ($manifest -join "`n"), [Text.UTF8Encoding]::new($false))
$copyStartedAt = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
& $python (Join-Path $PSScriptRoot 'mirror-device-backups.py') $manifestPath *> (Join-Path $destination 'latest-run.log')
if ($LASTEXITCODE -ne 0) { throw 'Device backup verification failed; remote copies preserved' }
$verifiedReceipt = Join-Path $destination 'latest-verified.json'
if ((Test-Path -LiteralPath $verifiedReceipt) -and ((Get-Content -LiteralPath $verifiedReceipt -Raw | ConvertFrom-Json).verified_at -ge $copyStartedAt)) {
    $retirement = Get-Content -LiteralPath $verifiedReceipt -Raw | & ssh -o BatchMode=yes -o ConnectTimeout=20 runr-vps 'sudo systemd-run --quiet --wait --pipe --collect -p EnvironmentFile=/etc/runr/customer-candidate-20261010/api.env -p EnvironmentFile=/etc/runr/connections-release.env /opt/runr/.venv/bin/python /opt/runr-ops/retire-device-archived-r2.py'
    if ($LASTEXITCODE -ne 0) { throw 'Historical R2 retirement failed; local archives remain safe' }
    [IO.File]::WriteAllText((Join-Path $destination 'historical-r2-retirement.json'), ($retirement -join "`n"), [Text.UTF8Encoding]::new($false))
}
Remove-Item -LiteralPath $manifestPath
