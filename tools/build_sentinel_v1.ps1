#requires -Version 7.0
param([ValidateRange(1,6)][int]$Attempt=1,[switch]$ValidateOnly,[switch]$ExtraAttemptAuthorized)
$ErrorActionPreference='Stop'
if($Attempt -gt 3 -and -not $ExtraAttemptAuthorized){throw 'Attempts 4-6 require explicit user authorization'}
. (Join-Path $PSScriptRoot 'env.ps1')
$project='sentinel_v1'
& (Join-Path $PSScriptRoot 'sync_hw.ps1') -Proj $project | Out-Host
$projectDir=Join-Path $env:REPO "build/work/adi_hdl/projects/fmcomms2/$project"
$prefix=if($ValidateOnly){'N4_validate'}else{'N4_implementation'}
$exitFile=Join-Path $env:REPO "logs/${prefix}_round${Attempt}_exit.txt"
if(Test-Path -LiteralPath $exitFile){throw "Existing attempt record must be preserved: $exitFile"}
Set-Content $exitFile 'RUNNING'
try {
    Push-Location $projectDir
    $env:ADI_MAX_OOC_JOBS='1'
    $env:SENTINEL_VALIDATE_ONLY=if($ValidateOnly){'1'}else{'0'}
    & (Join-Path $env:XILINX_ROOT 'Vivado/bin/vivado.bat') -mode batch -notrace `
        -source system_project.tcl -log (Join-Path $env:REPO "logs/${prefix}_round${Attempt}.log") `
        -journal (Join-Path $env:REPO "logs/${prefix}_round${Attempt}.jou")
    if($LASTEXITCODE -ne 0){throw "Vivado failed: $LASTEXITCODE"}
    Pop-Location
    if(-not $ValidateOnly){& (Join-Path $PSScriptRoot 'collect_hw.ps1') -Proj $project -Tag sentinel_v1}
    Set-Content $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content $exitFile '1'
    exit 1
}
