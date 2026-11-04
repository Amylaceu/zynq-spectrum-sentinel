#requires -Version 7.0
param([ValidateRange(1,3)][int]$Attempt=1,[switch]$ValidateOnly)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
if(-not(Test-Path build/work/x1_packaged_ip/cfar_core_x1/component.xml)) { throw 'Package X1 CFAR first' }
$prefix=if($ValidateOnly){'X1_v1b_validate'}else{'X1_v1b_implementation'}
$exitFile="logs/$($prefix)_r$($Attempt)_exit.txt"
if(Test-Path $exitFile) { throw 'Preserve previous attempt' }
if(-not $ValidateOnly -and (Test-Path board/overlay/sentinel_v1b)) { throw 'Preserve prior v1b artifacts before rebuilding' }
& (Join-Path $PSScriptRoot 'sync_hw.ps1') -Proj sentinel_v1b | Out-Host
$projectDir=Join-Path $env:REPO 'build/work/adi_hdl/projects/fmcomms2/sentinel_v1b'
Set-Content $exitFile 'RUNNING'
$code=0
try {
    Push-Location $projectDir
    $env:ADI_MAX_OOC_JOBS='1'
    $env:SENTINEL_VALIDATE_ONLY=if($ValidateOnly){'1'}else{'0'}
    & (Join-Path $env:XILINX_ROOT 'Vivado/bin/vivado.bat') -mode batch -notrace -source system_project.tcl -log (Join-Path $env:REPO "logs/$($prefix)_r$Attempt.log") -journal (Join-Path $env:REPO "logs/$($prefix)_r$Attempt.jou")
    if($LASTEXITCODE -ne 0) { throw 'v1b Vivado failed' }
} catch {
    $_ | Out-String | Write-Output
    $code=1
} finally { Pop-Location }
if($code -eq 0 -and -not $ValidateOnly) {
    try { & (Join-Path $PSScriptRoot 'collect_hw.ps1') -Proj sentinel_v1b -Tag sentinel_v1b }
    catch { $_ | Out-String | Write-Output; $code=1 }
}
Set-Content $exitFile "$code"
if($code) { exit $code }
