param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$prefix="logs/Y2_z2_lcd_package_r$Attempt"
if(Test-Path "$($prefix)_exit.txt") { throw 'Preserve prior attempt' }
Set-Content "$($prefix)_exit.txt" 'RUNNING'
try {
    & (Join-Path $env:XILINX_ROOT 'Vivado/bin/vivado.bat') -mode batch -notrace `
        -source build/scripts/package_z2_lcd.tcl -log "$prefix.log" -journal "$prefix.jou" `
        -tclargs lcd8080_engine_z2 src/rtl/lcd_z2 build/work/z2_packaged_ip
    if($LASTEXITCODE) { throw 'Z2 LCD packaging failed' }
    Set-Content "$($prefix)_exit.txt" '0'
} catch { $_ | Out-String | Write-Output;Set-Content "$($prefix)_exit.txt" '1';exit 1 }
