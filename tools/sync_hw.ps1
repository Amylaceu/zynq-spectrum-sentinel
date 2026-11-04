param([string]$Proj = 'fmcomms2_z20')
$ErrorActionPreference = 'Stop'
if ($Proj -notmatch '^[a-z][a-z0-9_]*$') { throw 'Invalid project name' }
. (Join-Path $PSScriptRoot 'env.ps1')
$reference = Join-Path $env:REPO 'third_party/hdl'
$worktree = Join-Path $env:REPO 'build/work/adi_hdl'
$source = Join-Path $env:REPO "src/hw/$Proj"
$sub = if ($Proj -eq 'fmcomms2_z20') {'z20'} else {$Proj}
$destination = Join-Path $worktree "projects/fmcomms2/$sub"
if (-not (Test-Path -LiteralPath $source -PathType Container)) { throw "Missing overlay: $source" }
$revision = & git -C $reference rev-parse HEAD
if ($LASTEXITCODE) { throw 'Missing ADI reference checkout' }
if (-not (Test-Path -LiteralPath $worktree)) {
    New-Item -ItemType Directory -Force (Split-Path $worktree) | Out-Null
    & git -C $reference worktree add --detach $worktree $revision | Out-Host
    if ($LASTEXITCODE) { throw 'Could not create isolated HDL build checkout' }
} else {
    $actualRoot = & git -C $worktree rev-parse --show-toplevel
    if ($LASTEXITCODE -or [IO.Path]::GetFullPath($actualRoot) -ne [IO.Path]::GetFullPath($worktree)) {
        throw 'Existing build path is not the expected independent Git worktree'
    }
    $actualRevision = & git -C $worktree rev-parse HEAD
    if ($LASTEXITCODE -or $actualRevision -ne $revision) {
        throw 'Existing HDL build checkout has another revision; review it before replacing any files'
    }
}
$resolvedDestination = [IO.Path]::GetFullPath($destination)
if (-not $resolvedDestination.StartsWith([IO.Path]::GetFullPath($worktree) + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Destination escapes isolated HDL build checkout'
}
New-Item -ItemType Directory -Path $destination -Force | Out-Null
Get-ChildItem -LiteralPath $source -File | Copy-Item -Destination $destination -Force
$env:ADI_HDL_DIR = $worktree
Write-Host "Overlay synchronized to isolated build checkout: $destination"
[pscustomobject]@{ HdlRoot=$worktree; ProjectDir=$destination; Revision=$revision }
