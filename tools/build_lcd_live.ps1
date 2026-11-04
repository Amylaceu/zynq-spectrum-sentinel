#requires -Version 7.0
param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$project='fmcomms2_z20_lcd_live'
& (Join-Path $PSScriptRoot 'sync_hw.ps1') -Proj $project | Out-Host
$projectDir=Join-Path $env:REPO "build/work/adi_hdl/projects/fmcomms2/$project"
$exitFile=Join-Path $env:REPO "logs/P5.4_lcd_live_round${Attempt}_exit.txt"
Set-Content $exitFile 'RUNNING'
try {
    Push-Location $projectDir
    $env:ADI_MAX_OOC_JOBS='1'
    & (Join-Path $env:XILINX_ROOT 'Vivado/bin/vivado.bat') -mode batch -notrace `
        -source system_project.tcl -log (Join-Path $env:REPO "logs/P5.4_lcd_live_round${Attempt}.log") `
        -journal (Join-Path $env:REPO "logs/P5.4_lcd_live_round${Attempt}.jou")
    if($LASTEXITCODE -ne 0){throw "Vivado failed: $LASTEXITCODE"}
    Pop-Location
    & (Join-Path $PSScriptRoot 'collect_hw.ps1') -Proj $project -Tag live_z20_lcd
    Set-Content $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content $exitFile '1'
    exit 1
}
