param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$exitFile="logs/N4_engine_round${Attempt}_exit.txt"
Set-Content $exitFile 'RUNNING'
try {
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_lcd8080_engine `
        -Srcs @('src/rtl/lcd/*.v','src/rtl/regs/lcd_ctrl_regs.v','src/rtl/spectrum/spec_display_reduce.v','sim/tb/tb_lcd8080_engine.sv')
    Set-Content $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content $exitFile '1';exit 1
}
