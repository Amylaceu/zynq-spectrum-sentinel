#requires -Version 7.0
param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$prefix="logs/Y2_z2_final_audit_r$Attempt"
if(Test-Path "$($prefix)_exit.txt"){throw 'Preserve prior audit'}
Set-Content "$($prefix)_exit.txt" 'RUNNING'
try {
    & "$env:XILINX_ROOT/Vivado/bin/vivado.bat" -mode batch -notrace -source build/scripts/audit_sentinel_z2.tcl -log "$prefix.log" -journal "$prefix.jou"
    if($LASTEXITCODE){throw 'Full-system timing/CDC audit failed'}
    & $env:ZSS_PYTHON tools/accept_sentinel_z2.py --attempt $Attempt
    if($LASTEXITCODE){throw 'Full-system artifact/resource acceptance failed'}
    Set-Content "$($prefix)_exit.txt" '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content "$($prefix)_exit.txt" '1'
    exit 1
}
