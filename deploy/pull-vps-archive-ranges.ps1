param([ValidateSet('history','releases')][string]$Label, [long]$Bytes, [int]$Connections = 16)
$ErrorActionPreference = 'Stop'
$destination = 'C:\Users\ahmed\Runr-Historical-Archives\2026-10-11'
$baseUrl = Get-Content (Join-Path $destination 'transfer-url.txt') -Raw
$chunkBytes = [long][Math]::Ceiling($Bytes / $Connections)
$transfers = @()
for ($index = 0; $index -lt $Connections; $index++) {
    $start = $index * $chunkBytes
    if ($start -ge $Bytes) { break }
    $end = [Math]::Min($Bytes - 1, $start + $chunkBytes - 1)
    $target = Join-Path $destination "$Label.range-$index"
    $arguments = @('--fail','--silent','--show-error','--retry','5','--retry-delay','2','--range',"$start-$end",'--output',$target,"$baseUrl/$Label")
    $process = Start-Process curl.exe -ArgumentList $arguments -WindowStyle Hidden -PassThru
    $transfers += [pscustomobject]@{Process=$process;Target=$target;Expected=$end-$start+1}
}
foreach ($transfer in $transfers) {
    $transfer.Process.WaitForExit()
    if ($transfer.Process.ExitCode -ne 0 -or (Get-Item -LiteralPath $transfer.Target).Length -ne $transfer.Expected) { throw "Incomplete range: $($transfer.Target); originals retained" }
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
Write-Output "Reassembled $Label archive: $Bytes bytes; verify SHA256 before finalize."
