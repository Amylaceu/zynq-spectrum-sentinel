param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$exitFile="logs/N2_regs_round${Attempt}_exit.txt"
Set-Content $exitFile 'RUNNING'
try {
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_spec_regs `
        -Srcs @('src/rtl/regs/spec_ctrl_regs.v','sim/tb/tb_spec_regs.sv') `
        -MemoryFiles @('sim/tb/regs/spec_ctrl_defs.vh')
    Set-Content $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content $exitFile '1'
    exit 1
}
