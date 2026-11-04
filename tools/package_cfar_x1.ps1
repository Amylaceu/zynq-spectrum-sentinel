param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$log="logs/X1_cfar_package_r$Attempt.log"
if(Test-Path $log) { throw 'Preserve previous package log' }
& "$env:XILINX_ROOT/Vivado/bin/vivado.bat" -mode batch -notrace -source build/scripts/package_cfar_x1.tcl -log $log -journal "logs/X1_cfar_package_r$Attempt.jou"
if($LASTEXITCODE -ne 0) { throw 'X1 package failed' }
if(-not(Select-String -LiteralPath $log -SimpleMatch 'X1_CFAR_PACKAGE_PASS' -Quiet)) { throw 'Missing package completion marker' }
