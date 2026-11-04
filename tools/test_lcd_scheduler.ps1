param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$exitFile="logs/N4_scheduler_round${Attempt}_exit.txt"
Set-Content $exitFile 'RUNNING'
try {
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_lcd_render_scheduler `
        -Srcs @('src/rtl/lcd/lcd_trace_pixel.v','src/rtl/lcd/lcd_render_scheduler.v','src/rtl/lcd/lcd8080_region.v','sim/tb/tb_lcd_render_scheduler.sv') `
        -MemoryFiles @('data/reference/lcd/n4_pixel_spec.hex','data/reference/lcd/n4_pixel_thr.hex',
            'data/reference/lcd/n4_pixel_expected.hex','data/reference/lcd/n4_waterfall_expected.hex')
    Set-Content $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content $exitFile '1';exit 1
}
