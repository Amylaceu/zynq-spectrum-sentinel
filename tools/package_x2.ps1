#requires -Version 7.0
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
foreach($ip in @('spec_front_x2','cfar_core_x2')) {
    & "$env:XILINX_ROOT/Vivado/bin/vivado.bat" -mode batch -notrace -source build/scripts/package_x2.tcl `
        -log "logs/X2_package_$ip.log" -journal "logs/X2_package_$ip.jou" -tclargs $ip
    if($LASTEXITCODE){throw "X2 IP packaging failed: $ip"}
}
