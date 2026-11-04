param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$exitFile="logs/N4_lcd_bus_round${Attempt}_exit.txt"
Set-Content $exitFile 'RUNNING'
try {
    & $env:ZSS_PYTHON tools/export_lcd_init.py
    if($LASTEXITCODE){throw 'LCD ROM extraction failed'}
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_lcd8080_bus `
        -Srcs @('src/rtl/lcd/lcd8080_bus.v','sim/tb/tb_lcd8080_bus.sv') `
        -MemoryFiles @('data/reference/lcd/n4_lcd_init_bus.hex')
    Set-Content $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content $exitFile '1';exit 1
}
