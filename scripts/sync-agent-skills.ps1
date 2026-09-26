param(
    [string]$Source = ".agents/skills",
    [string]$Destination = ".cline/skills"
)

$ErrorActionPreference = "Stop"

function Resolve-RepoPath {
    param([string]$Path)

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }

    return [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Path))
}

function Test-KebabCase {
    param([string]$Name)
    return $Name -match '^[a-z0-9]+(-[a-z0-9]+)*$'
}

function Get-FrontmatterField {
    param(
        [string]$Text,
        [string]$Field
    )

    $match = [regex]::Match($Text, "(?ms)^---\s*\r?\n(?<yaml>.*?)\r?\n---\s*\r?\n")
    if (-not $match.Success) {
        throw "Missing YAML frontmatter"
    }

    $yaml = $match.Groups["yaml"].Value
    $fieldMatch = [regex]::Match($yaml, "(?ms)^$([regex]::Escape($Field)):\s*(?<value>.*?)(?=^\S|\z)")
    if (-not $fieldMatch.Success) {
        throw "Missing '$Field' field"
    }

    return $fieldMatch.Groups["value"].Value.Trim().Trim('"').Trim("'").Trim()
}

$sourcePath = Resolve-RepoPath $Source
$destinationPath = Resolve-RepoPath $Destination
$repoPath = [System.IO.Path]::GetFullPath((Get-Location))

if (-not $sourcePath.StartsWith($repoPath, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Source must be inside this repository: $sourcePath"
}

if (-not $destinationPath.StartsWith($repoPath, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Destination must be inside this repository: $destinationPath"
}

if (-not (Test-Path -LiteralPath $sourcePath -PathType Container)) {
    throw "Source skills directory does not exist: $sourcePath"
}

New-Item -ItemType Directory -Force -Path $destinationPath | Out-Null

$skills = Get-ChildItem -LiteralPath $sourcePath -Directory | Sort-Object Name
if ($skills.Count -eq 0) {
    throw "No skill directories found in $sourcePath"
}

foreach ($skill in $skills) {
    if (-not (Test-KebabCase $skill.Name)) {
        throw "Skill directory is not lowercase kebab-case: $($skill.Name)"
    }

    $skillFile = Join-Path $skill.FullName "SKILL.md"
    if (-not (Test-Path -LiteralPath $skillFile -PathType Leaf)) {
        throw "Missing SKILL.md for skill: $($skill.Name)"
    }

    $text = Get-Content -LiteralPath $skillFile -Raw
    $name = Get-FrontmatterField -Text $text -Field "name"
    $description = Get-FrontmatterField -Text $text -Field "description"

    if ($name -ne $skill.Name) {
        throw "Skill '$($skill.Name)' has frontmatter name '$name'"
    }

    if ([string]::IsNullOrWhiteSpace($description) -or $description.Length -lt 40) {
        throw "Skill '$($skill.Name)' has an empty or too-short description"
    }

    $target = Join-Path $destinationPath $skill.Name
    $temp = Join-Path $destinationPath ".$($skill.Name).tmp"

    if (Test-Path -LiteralPath $temp) {
        Remove-Item -LiteralPath $temp -Recurse -Force
    }

    Copy-Item -LiteralPath $skill.FullName -Destination $temp -Recurse -Force

    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }

    Move-Item -LiteralPath $temp -Destination $target
    Write-Host "Synced $($skill.Name)"
}

Write-Host "Synced $($skills.Count) skills from $Source to $Destination"
