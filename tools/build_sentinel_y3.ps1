#requires -Version 7.0
param([ValidateRange(1,3)][int]$Attempt=1,[switch]$ValidateOnly)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
if(-not(Test-Path build/work/x5_cfar_packaged_ip/cfar_core_x5/component.xml)) { throw 'Package X5 CFAR first' }
if(-not(Test-Path build/work/x5_packaged_ip/lcd8080_engine_x5/component.xml)) { throw 'Package X5 LCD first' }
$prefix=if($ValidateOnly){'Y3_full_validate'}else{'Y3_full_implementation'}
$exitFile="logs/$($prefix)_r$($Attempt)_exit.txt"
if(Test-Path $exitFile) { throw 'Preserve previous attempt' }
if(-not $ValidateOnly -and (Test-Path board/overlay/sentinel_y3)) { throw 'Preserve prior v1d artifacts before rebuilding' }
if(-not $ValidateOnly) {
    & $env:ZSS_PYTHON tools/freeze_y3_build.py --attempt $Attempt --verify
    if($LASTEXITCODE){throw 'Implementation input freeze failed verification'}
}
& (Join-Path $PSScriptRoot 'sync_hw.ps1') -Proj sentinel_y3 | Out-Host
$projectDir=Join-Path $env:REPO 'build/work/adi_hdl/projects/fmcomms2/sentinel_y3'
Set-Content $exitFile 'RUNNING'
$code=0
try {
    Push-Location $projectDir
    $env:ADI_MAX_OOC_JOBS='1'
    $env:ADI_AUTOFIX_MAX_ATTEMPTS='2'
    $env:SENTINEL_VALIDATE_ONLY=if($ValidateOnly){'1'}else{'0'}
    & (Join-Path $env:XILINX_ROOT 'Vivado/bin/vivado.bat') -mode batch -notrace -source system_project.tcl -log (Join-Path $env:REPO "logs/$($prefix)_r$Attempt.log") -journal (Join-Path $env:REPO "logs/$($prefix)_r$Attempt.jou")
    if($LASTEXITCODE -ne 0) { throw 'Y3 Vivado failed' }
} catch {
    $_ | Out-String | Write-Output
    $code=1
} finally { Pop-Location }
if($code -eq 0 -and -not $ValidateOnly) {
    try { & (Join-Path $PSScriptRoot 'collect_hw.ps1') -Proj sentinel_y3 -Tag sentinel_y3 }
    catch { $_ | Out-String | Write-Output; $code=1 }
}
Set-Content $exitFile "$code"
if($code) { exit $code }
