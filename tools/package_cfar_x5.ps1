#requires -Version 7.0
param([ValidateRange(1,3)][int]$Attempt=2)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$prefix="logs/X5_cfar_package_r$Attempt"
if(Test-Path "$($prefix)_exit.txt"){throw 'Preserve previous packaging evidence'}
Set-Content "$($prefix)_exit.txt" 'RUNNING'
try {
    & "$env:XILINX_ROOT/Vivado/bin/vivado.bat" -mode batch -notrace -source build/scripts/package_cfar_x5.tcl -log "$prefix.log" -journal "$prefix.jou"
    if($LASTEXITCODE){throw 'X5 CFAR packaging failed'}
    if(-not(Select-String -LiteralPath "$prefix.log" -SimpleMatch 'X5_CFAR_PACKAGE_PASS' -Quiet)){throw 'Missing package completion marker'}
    Set-Content "$($prefix)_exit.txt" '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content "$($prefix)_exit.txt" '1'
    exit 1
}
