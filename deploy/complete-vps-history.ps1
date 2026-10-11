$ErrorActionPreference = 'Stop'
$destination = 'C:\Users\ahmed\Runr-Historical-Archives\2026-10-11'
$archives = @(
    @{Label='releases';Bytes=947118748;Sha='5d1e0b103259c92c2e2e6e151e93b4ae114dbc60200cfbc505b470dda6e7832e'},
    @{Label='history';Bytes=5688671964;Sha='fbef3a29c7656fa3334ecfc16e88996424e56a5f6961e30964b306f32e58c3f3'}
)
foreach ($archive in $archives) {
    $completed = $false
    for ($attempt = 0; $attempt -lt 6 -and -not $completed; $attempt++) {
        try {
            & "$PSScriptRoot/pull-vps-archive-ranges.ps1" -Label $archive.Label -Bytes $archive.Bytes -ExpectedSha256 $archive.Sha -Connections 16
            $completed = $true
        } catch {
            $_ | Out-String | Add-Content (Join-Path $destination 'completion-errors.txt')
            Start-Sleep -Seconds 15
        }
    }
    if (-not $completed) { throw "Transfer failed for $($archive.Label); VPS originals preserved" }
    $file = Join-Path $destination "$($archive.Label).tar.gz"
    tar -tzf $file | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Archive unreadable; VPS originals preserved' }
    "SHA256=$($archive.Sha)`nArchive=$file`nVerified=$([DateTimeOffset]::Now.ToString('o'))" | Set-Content (Join-Path $destination "$($archive.Label).verified.txt")
    ssh -o BatchMode=yes -o ConnectTimeout=20 runr-vps "sudo env RUNR_HISTORY_ARCHIVE_LABEL=$($archive.Label) bash /opt/runr-ops/archive-vps-history.sh finalize $($archive.Sha)"
    if ($LASTEXITCODE -ne 0) { throw 'Source comparison/finalization failed; inspect VPS receipts' }
    ssh -o BatchMode=yes runr-vps "sudo cat /srv/runr/ops/$($archive.Label)-archive-20261011/finalized.txt; sudo cat /srv/runr/ops/$($archive.Label)-archive-20261011/disk-after.txt" | Set-Content (Join-Path $destination "$($archive.Label).completed.txt")
    if ($LASTEXITCODE -ne 0) { throw 'Cleanup receipt retrieval failed' }
}
ssh -o BatchMode=yes runr-vps 'set -e; sudo bash /opt/runr-ops/stop-vps-archive-transfer.sh; sudo systemctl start runr-storage-budget.service; df -B1 /; curl -fsS https://app.userunr.com/health/ready' | Set-Content (Join-Path $destination 'final-vps-status.txt')
if ($LASTEXITCODE -ne 0) { throw 'Final verification failed; inspect final-vps-status.txt' }
'Completed verified archive cleanup' | Set-Content (Join-Path $destination 'COMPLETE.txt')
