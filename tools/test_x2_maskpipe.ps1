#requires -Version 7.0
param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$prefix="logs/X2_maskpipe_r$Attempt"
if(Test-Path "$($prefix)_exit.txt"){throw 'Preserve previous mask-pipeline evidence'}
Set-Content "$($prefix)_exit.txt" 'RUNNING'
try {
    $memories=@(Get-ChildItem data/reference/cfar/x1_guard8/*.hex | ForEach-Object {"data/reference/cfar/x1_guard8/$($_.Name)"})
    $memories+='data/reference/spectrum/spec_log_mantissa.hex'
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_cfar_maskpipe_x2 -Srcs @(
        'src/rtl/cfar_x1/*.v','src/rtl/cfar/cfar_occupancy.v',
        'src/rtl/common/axis_broadcast2.v','src/rtl/x2_opt/cfar_core_maskpipe_x2.v',
        'sim/tb/tb_cfar_maskpipe_x2.sv') -MemoryFiles $memories
    Copy-Item sim/results/tb_cfar_maskpipe_x2.log "$($prefix)_simulation.log"
    & $env:ZSS_PYTHON tools/verify_x2_maskpipe.py --attempt $Attempt
    if($LASTEXITCODE){throw 'Mask pipeline independent verification failed'}
    Set-Content "$($prefix)_exit.txt" '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content "$($prefix)_exit.txt" '1';exit 1
}
