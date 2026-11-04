param(
    [Parameter(Mandatory)][string]$OutputDirectory,
    [switch]$Deploy,
    [switch]$Replace
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$pythonExe = Join-Path $repoRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $pythonExe)) { throw 'Create the project Python environment first' }
$releaseArgs = @((Join-Path $PSScriptRoot 'release_board.py'), '--output', $OutputDirectory)
if ($Deploy) { $releaseArgs += '--deploy' }
if ($Replace) { $releaseArgs += '--replace' }
& $pythonExe @releaseArgs
if ($LASTEXITCODE -ne 0) { throw "Release operation failed: $LASTEXITCODE" }
