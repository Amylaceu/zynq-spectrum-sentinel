#requires -Version 7.0
param([switch]$Resume, [ValidateRange(1,3)][int]$Attempt = 1)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$project = 'fmcomms2_z20_lcd'
$sync = & (Join-Path $PSScriptRoot 'sync_hw.ps1') -Proj $project
$projectDir = Join-Path $env:REPO "build/work/adi_hdl/projects/fmcomms2/$project"
$exitFile = Join-Path $env:REPO 'logs/P5.3_build_exit.txt'
Set-Content -LiteralPath $exitFile -Value 'RUNNING'
try {
    Push-Location $projectDir
    $env:ADI_MAX_OOC_JOBS = '1'
    $source = if ($Resume) { Join-Path $env:REPO 'build/scripts/resume_rf_lcd.tcl' } else { 'system_project.tcl' }
    $suffix = if ($Attempt -gt 1) { "_round$Attempt" } else { '' }
    & (Join-Path $env:XILINX_ROOT 'Vivado/bin/vivado.bat') -mode batch -notrace `
        -source $source -log (Join-Path $env:REPO "logs/P5.3_vivado$suffix.log") `
        -journal (Join-Path $env:REPO "logs/P5.3_vivado$suffix.jou")
    if ($LASTEXITCODE -ne 0) { throw "Vivado failed with $LASTEXITCODE" }
    Pop-Location
    & (Join-Path $PSScriptRoot 'collect_hw.ps1') -Proj $project -Tag bringup_z20_lcd
    Set-Content -LiteralPath $exitFile -Value '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content -LiteralPath $exitFile -Value '1'
    exit 1
}
