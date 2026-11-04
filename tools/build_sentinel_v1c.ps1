#requires -Version 7.0
param([ValidateRange(1,3)][int]$Attempt=1,[switch]$ValidateOnly)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
if(-not(Test-Path build/work/x2_packaged_ip/cfar_core_x2/component.xml)) { throw 'Package X2 CFAR first' }
$prefix=if($ValidateOnly){'X2_v1c_validate'}else{'X2_v1c_implementation'}
$exitFile="logs/$($prefix)_r$($Attempt)_exit.txt"
if(Test-Path $exitFile) { throw 'Preserve previous attempt' }
if(-not $ValidateOnly -and (Test-Path board/overlay/sentinel_v1c)) { throw 'Preserve prior v1c artifacts before rebuilding' }
if(-not(Test-Path sim/results/x2_simulation_acceptance.json)){throw 'X2 simulation acceptance required'}
$simulation=Get-Content sim/results/x2_simulation_acceptance.json -Raw | ConvertFrom-Json
if($simulation.status -ne 'PASS'){throw 'X2 simulation did not pass'}
& $env:ZSS_PYTHON (Join-Path $PSScriptRoot 'freeze_x2_build.py') --attempt $Attempt --verify
if($LASTEXITCODE){throw 'X2 frozen input verification failed'}
& (Join-Path $PSScriptRoot 'sync_hw.ps1') -Proj sentinel_v1c | Out-Host
$projectDir=Join-Path $env:REPO 'build/work/adi_hdl/projects/fmcomms2/sentinel_v1c'
Set-Content $exitFile 'RUNNING'
$code=0
try {
    Push-Location $projectDir
    $env:ADI_MAX_OOC_JOBS='1'
    $env:SENTINEL_VALIDATE_ONLY=if($ValidateOnly){'1'}else{'0'}
    & (Join-Path $env:XILINX_ROOT 'Vivado/bin/vivado.bat') -mode batch -notrace -source system_project.tcl -log (Join-Path $env:REPO "logs/$($prefix)_r$Attempt.log") -journal (Join-Path $env:REPO "logs/$($prefix)_r$Attempt.jou")
    if($LASTEXITCODE -ne 0) { throw 'v1c Vivado failed' }
} catch {
    $_ | Out-String | Write-Output
    $code=1
} finally { Pop-Location }
if($code -eq 0 -and -not $ValidateOnly) {
    try { & (Join-Path $PSScriptRoot 'collect_hw.ps1') -Proj sentinel_v1c -Tag sentinel_v1c }
    catch { $_ | Out-String | Write-Output; $code=1 }
}
Set-Content $exitFile "$code"
if($code) { exit $code }
