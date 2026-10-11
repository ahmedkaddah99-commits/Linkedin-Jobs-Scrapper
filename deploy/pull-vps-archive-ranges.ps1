param([ValidateSet('history','releases')][string]$Label, [long]$Bytes, [int]$Connections = 32, [Parameter(Mandatory=$true)][string]$ExpectedSha256)
$ErrorActionPreference = 'Stop'
$destination = 'C:\Users\ahmed\Runr-Historical-Archives\2026-10-11'
$baseUrl = (Get-Content (Join-Path $destination 'transfer-url.txt') -Raw).Trim()
$password = (Get-Content (Join-Path $destination 'transfer-password.txt') -Raw).Trim()
$chunkBytes = 8MB
$count = [int][Math]::Ceiling($Bytes / $chunkBytes)
$transfers = @()
for ($index = 0; $index -lt $count; $index++) {
    while (@($transfers | Where-Object { $null -ne $_.Process -and -not $_.Process.HasExited }).Count -ge $Connections) { Start-Sleep -Milliseconds 200 }
    $start = $index * $chunkBytes
    if ($start -ge $Bytes) { break }
    $end = [Math]::Min($Bytes - 1, $start + $chunkBytes - 1)
    $target = Join-Path $destination "$Label.chunk-$index"
    if ((Test-Path -LiteralPath $target) -and (Get-Item -LiteralPath $target).Length -eq $end-$start+1) {
        $transfers += [pscustomobject]@{Process=$null;Target=$target;Expected=$end-$start+1}
        continue
    }
    $arguments = @('--fail','--silent','--show-error','--retry','5','--retry-delay','2','--connect-timeout','20','--max-time','300','--user',"archive:$password",'--range',"$start-$end",'--output',$target,"$baseUrl/$Label")
    $process = Start-Process curl.exe -ArgumentList $arguments -WindowStyle Hidden -PassThru
    $transfers += [pscustomobject]@{Process=$process;Target=$target;Expected=$end-$start+1}
}
foreach ($transfer in $transfers) {
    if ($null -ne $transfer.Process) { $transfer.Process.WaitForExit() }
    if (($null -ne $transfer.Process -and $transfer.Process.ExitCode -ne 0) -or (Get-Item -LiteralPath $transfer.Target).Length -ne $transfer.Expected) { throw "Incomplete range: $($transfer.Target); originals retained" }
}
$archive = Join-Path $destination "$Label.tar.gz"
$outputStream = [IO.File]::Create($archive)
try {
    foreach ($transfer in $transfers) {
        $inputStream = [IO.File]::OpenRead($transfer.Target)
        try { $inputStream.CopyTo($outputStream) } finally { $inputStream.Dispose() }
    }
} finally { $outputStream.Dispose() }
if ((Get-Item -LiteralPath $archive).Length -ne $Bytes) { throw 'Reassembled length mismatch' }
$actualSha256 = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualSha256 -ne $ExpectedSha256.ToLowerInvariant()) { throw 'Archive SHA256 mismatch; originals retained' }
Write-Output "Verified $Label archive: $Bytes bytes; SHA256 $actualSha256"
