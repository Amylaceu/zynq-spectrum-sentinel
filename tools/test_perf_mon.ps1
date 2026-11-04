param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$exitFile="logs/N4_perf_round${Attempt}_exit.txt"
Set-Content $exitFile 'RUNNING'
try {
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_perf_mon `
        -Srcs @('src/rtl/perf/*.v','src/rtl/regs/perf_ctrl_regs.v','sim/tb/tb_perf_mon.sv')
    Set-Content $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content $exitFile '1';exit 1
}
