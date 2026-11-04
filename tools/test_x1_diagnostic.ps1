#requires -Version 7.0
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$exitFile='logs/X1_diagnostic_sim_r1_exit.txt'
if(Test-Path $exitFile){throw 'Preserve prior diagnostic attempt'}
Set-Content $exitFile 'RUNNING'
try {
    & $env:ZSS_PYTHON tools/export_x1_diagnostic_vectors.py
    if($LASTEXITCODE){throw 'Vector generation failed'}
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_x1_diagnostic -Srcs @(
        'src/rtl/spectrum/spec_welch.v','src/rtl/common/sentinel_capture.v',
        'src/rtl/common/axis_broadcast2.v','src/rtl/cfar_x1/*.v',
        'src/rtl/cfar/cfar_occupancy.v','sim/tb/tb_x1_diagnostic.sv'
    ) -MemoryFiles @('diag_input.hex','diag_power.hex','diag_stats.hex' | ForEach-Object {"data/reference/cfar/x1_diagnostic_r1/$_"})
    Set-Content $exitFile '0'
} catch {
    Write-Output ($_ | Out-String)
    Set-Content $exitFile '1'
    exit 1
}
