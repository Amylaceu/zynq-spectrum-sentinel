#requires -Version 7.0
param([ValidateRange(1,3)][int]$Attempt=2)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$prefix="logs/Z10_cfar_r$Attempt"
if(Test-Path "$($prefix)_exit.txt"){throw 'Preserve prior CFAR test evidence'}
Set-Content "$($prefix)_exit.txt" 'RUNNING'
try {
    $memories=@(Get-ChildItem data/reference/cfar/x1_guard8/*.hex | ForEach-Object {"data/reference/cfar/x1_guard8/$($_.Name)"})
    $memories+='data/reference/spectrum/spec_log_mantissa.hex'
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_cfar_v2 -Srcs @(
        'src/rtl/cfar_v2/*.v','src/rtl/cfar_x1/cfar_detect_x1.v',
        'src/rtl/cfar_x1/cfar_x1_regs.v','src/rtl/cfar/cfar_occupancy.v',
        'src/rtl/common/axis_broadcast2.v','sim/tb/tb_cfar_v2.sv') -MemoryFiles $memories
    & $env:ZSS_PYTHON tools/verify_cfar_v2.py --attempt $Attempt
    if($LASTEXITCODE){throw 'Independent X5 CFAR comparison failed'}
    Set-Content "$($prefix)_exit.txt" '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content "$($prefix)_exit.txt" '1'
    exit 1
}
