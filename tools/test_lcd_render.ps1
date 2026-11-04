param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$exitFile="logs/N4_render_round${Attempt}_exit.txt"
Set-Content $exitFile 'RUNNING'
try {
    & $env:ZSS_PYTHON tools/export_lcd_pixels.py
    if($LASTEXITCODE){throw 'LCD pixels reference failed'}
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_lcd_trace_pixel `
        -Srcs @('src/rtl/lcd/lcd_trace_pixel.v','sim/tb/tb_lcd_trace_pixel.sv') `
        -MemoryFiles @('data/reference/lcd/n4_pixel_spec.hex','data/reference/lcd/n4_pixel_thr.hex',
            'data/reference/lcd/n4_pixel_expected.hex','data/reference/lcd/n4_waterfall_expected.hex')
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_lcd_snapshot `
        -Srcs @('src/rtl/lcd/lcd_snapshot.v','sim/tb/tb_lcd_snapshot.sv')
    Set-Content $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content $exitFile '1';exit 1
}
