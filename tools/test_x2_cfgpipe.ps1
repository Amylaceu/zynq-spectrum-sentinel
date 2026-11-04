#requires -Version 7.0
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$prefix='logs/X2_maskpipe_r3'
if(Test-Path "$($prefix)_exit.txt"){throw 'Preserve third/final experiment'}
Set-Content "$($prefix)_exit.txt" 'RUNNING'
try {
    $memories=@(Get-ChildItem data/reference/cfar/x1_guard8/*.hex | ForEach-Object {"data/reference/cfar/x1_guard8/$($_.Name)"})
    $memories+='data/reference/spectrum/spec_log_mantissa.hex'
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_cfar_cfgpipe_x2 -Srcs @(
        'src/rtl/cfar_x1/*.v','src/rtl/cfar/cfar_occupancy.v','src/rtl/common/axis_broadcast2.v',
        'src/rtl/x2_opt/cfar_core_cfgpipe_x2.v','sim/tb/tb_cfar_cfgpipe_x2.sv') -MemoryFiles $memories
    & $env:ZSS_PYTHON tools/verify_x2_cfgpipe.py
    if($LASTEXITCODE){throw 'Independent verification failed'}
    Set-Content "$($prefix)_exit.txt" '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content "$($prefix)_exit.txt" '1';exit 1
}
