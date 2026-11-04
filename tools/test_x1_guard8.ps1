param([switch]$ResumePrepared, [ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
if(Test-Path "logs/X1_guard8_sim_r$Attempt.log"){throw 'Preserve previous simulation log'}
Start-Transcript -Path "logs/X1_guard8_sim_r$Attempt.log" | Out-Null
try {
    if(-not $ResumePrepared) {
        & $env:ZSS_PYTHON tools/verify_x1_guard8_sim.py --prepare
        if($LASTEXITCODE){throw 'Preparation failed'}
    }
    $memories=@(Get-ChildItem 'data/reference/cfar/x1_guard8/*.hex' | ForEach-Object {"data/reference/cfar/x1_guard8/$($_.Name)"})
    $memories+='data/reference/spectrum/spec_log_mantissa.hex'
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_cfar_guard8 -Srcs @(
        'src/rtl/cfar_x1/*.v','src/rtl/cfar/cfar_occupancy.v',
        'src/rtl/common/axis_broadcast2.v','sim/tb/tb_cfar_guard8.sv'
    ) -MemoryFiles $memories
    & $env:ZSS_PYTHON tools/verify_x1_guard8_sim.py
    if($LASTEXITCODE){throw 'RTL/model verification failed'}
} finally {Stop-Transcript | Out-Null}
