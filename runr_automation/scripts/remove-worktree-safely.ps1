param(
    [Parameter(Mandatory = $true)][string]$RepositoryPath,
    [Parameter(Mandatory = $true)][string]$WorktreePath
)

$ErrorActionPreference = 'Stop'

$repository = (Resolve-Path -LiteralPath $RepositoryPath).Path
$worktree = (Resolve-Path -LiteralPath $WorktreePath).Path
$gitRoot = (& git -C $repository rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or -not $gitRoot) {
    throw "Not a Git repository: $repository"
}

$gitRoot = [System.IO.Path]::GetFullPath($gitRoot).TrimEnd('\', '/')
$worktree = [System.IO.Path]::GetFullPath($worktree).TrimEnd('\', '/')
if ([string]::Equals($gitRoot, $worktree, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Refusing to remove the shared checkout.'
}

$registered = @(& git -C $gitRoot worktree list --porcelain |
    Where-Object { $_ -like 'worktree *' } |
    ForEach-Object { [System.IO.Path]::GetFullPath($_.Substring(9)).TrimEnd('\', '/') })
if ($LASTEXITCODE -ne 0 -or -not @($registered | Where-Object {
    [string]::Equals($_, $worktree, [System.StringComparison]::OrdinalIgnoreCase)
}).Count) {
    throw "Path is not an exact registered worktree: $worktree"
}

foreach ($entry in Get-ChildItem -Force -LiteralPath $worktree) {
    if ($entry.Name -ne '.venv' -and ($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw "Refusing to remove worktree with another top-level reparse point: $($entry.FullName)"
    }
}

$venvPath = Join-Path $worktree '.venv'
$venv = Get-Item -Force -LiteralPath $venvPath -ErrorAction SilentlyContinue
if ($venv -and ($venv.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
    if ($venv.LinkType -notin @('Junction', 'SymbolicLink')) {
        throw "Unsupported .venv reparse point: $venvPath"
    }
    # Windows PowerShell 5.1 Remove-Item can throw for junctions. A nonrecursive
    # directory delete unlinks the reparse point without traversing its target.
    [System.IO.Directory]::Delete($venvPath)
    if (Get-Item -Force -LiteralPath $venvPath -ErrorAction SilentlyContinue) {
        throw "Could not detach .venv link: $venvPath"
    }
}

& git -C $gitRoot worktree remove $worktree
if ($LASTEXITCODE -ne 0) {
    throw "Git refused to remove worktree (local changes may remain): $worktree"
}
