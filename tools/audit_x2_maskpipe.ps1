#requires -Version 7.0
param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$prefix="logs/X2_maskpipe_timing_r$Attempt"
if(Test-Path "$($prefix)_exit.txt"){throw 'Preserve previous timing experiment'}
Set-Content "$($prefix)_exit.txt" 'RUNNING'
try {
    & "$env:XILINX_ROOT/Vivado/bin/vivado.bat" -mode batch -notrace `
        -source build/scripts/audit_x2_maskpipe.tcl -log "$prefix.log" -journal "$prefix.jou" -tclargs $Attempt
    if($LASTEXITCODE){throw 'CFAR mask timing comparison failed'}
    Set-Content "$($prefix)_exit.txt" '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content "$($prefix)_exit.txt" '1';exit 1
}
