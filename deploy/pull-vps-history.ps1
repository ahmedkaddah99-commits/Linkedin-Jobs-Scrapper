param([ValidateSet('history','releases')][string]$Label = 'history', [string]$Destination = 'C:\Users\ahmed\Runr-Historical-Archives\2026-10-11', [switch]$SkipDownload, [switch]$TunnelTransfer)
$ErrorActionPreference = 'Stop'
$remoteRoot = "/srv/runr/ops/$Label-archive-20261011"
New-Item -ItemType Directory -Force $Destination | Out-Null
$localArchive = Join-Path $Destination "$Label.tar.gz"
while ($true) {
    ssh -o BatchMode=yes runr-vps "sudo test -f $remoteRoot/history.sha256"
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 15
}
# Grant only the SSH account access to the protected transfer directory.
ssh runr-vps "sudo chgrp runradmin $remoteRoot $remoteRoot/history.tar.gz $remoteRoot/history.sha256 $remoteRoot/paths.txt $remoteRoot/archive-members.txt; sudo chmod 750 $remoteRoot; sudo chmod 640 $remoteRoot/history.tar.gz $remoteRoot/history.sha256 $remoteRoot/paths.txt $remoteRoot/archive-members.txt"
if ($LASTEXITCODE -ne 0) { throw 'Cannot grant archive transfer access' }
if (-not $SkipDownload) {
    if ($TunnelTransfer) {
        curl.exe --fail --silent --show-error --output $localArchive "http://127.0.0.1:18765/$Label-archive-20261011/history.tar.gz"
    } else {
    scp -O -o BatchMode=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 "runr-vps:$remoteRoot/history.tar.gz" $localArchive
    }
    if ($LASTEXITCODE -ne 0) { throw 'Archive download failed' }
}
foreach ($metadata in @(@('history.sha256',"$Label.remote.sha256"),@('paths.txt',"$Label.paths.txt"),@('archive-members.txt',"$Label.members.txt"))) {
    $target = Join-Path $Destination $metadata[1]
    if ($TunnelTransfer) {
        curl.exe --fail --silent --show-error --output $target "http://127.0.0.1:18765/$Label-archive-20261011/$($metadata[0])"
    } else { scp -O "runr-vps:$remoteRoot/$($metadata[0])" $target }
    if ($LASTEXITCODE -ne 0) { throw 'Metadata download failed; originals retained' }
}
$expected = ((Get-Content (Join-Path $Destination "$Label.remote.sha256") -Raw).Trim() -split '\s+')[0]
$actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $localArchive).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'Local archive SHA256 mismatch; VPS originals retained' }
tar -tzf $localArchive | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Local archive unreadable; VPS originals retained' }
"SHA256=$actual`nArchive=$localArchive`nVerified=$([DateTimeOffset]::Now.ToString('o'))" | Set-Content (Join-Path $Destination "$Label.verified.txt")
ssh runr-vps "sudo env RUNR_HISTORY_ARCHIVE_LABEL=$Label bash /opt/runr-ops/archive-vps-history.sh finalize $actual"
if ($LASTEXITCODE -ne 0) { throw 'VPS comparison/finalize failed; inspect receipts' }
ssh runr-vps "sudo cat $remoteRoot/disk-after.txt" | Set-Content (Join-Path $Destination "$Label.disk-after.txt")
Write-Output "Archived and verified: $localArchive ($actual)"
