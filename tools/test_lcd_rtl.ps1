$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$out=Join-Path $env:REPO 'build/sim_lcd'
New-Item -ItemType Directory -Force $out | Out-Null
Set-Location $out
& "$env:XILINX_ROOT/Vivado/bin/xvlog.bat" --sv "$env:REPO/src/hw/fmcomms2_z20_lcd_live/lcd_j22_framebuffer.v" "$env:REPO/sim/tb/tb_lcd_j22_framebuffer.sv"
if($LASTEXITCODE){exit 1}
& "$env:XILINX_ROOT/Vivado/bin/xelab.bat" tb_lcd_j22_framebuffer -s lcd_test
if($LASTEXITCODE){exit 1}
& "$env:XILINX_ROOT/Vivado/bin/xsim.bat" lcd_test -runall
exit $LASTEXITCODE
