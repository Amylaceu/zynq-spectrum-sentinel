#requires -Version 7.0
param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$prefix="logs/X2_timing_ooc_r$Attempt"
if(Test-Path "$($prefix)_exit.txt"){throw 'Preserve previous OOC audit'}
Set-Content "$($prefix)_exit.txt" 'RUNNING'
try {
    & "$env:XILINX_ROOT/Vivado/bin/vivado.bat" -mode batch -notrace `
        -source build/scripts/audit_x2_timing_candidates.tcl `
        -log "$prefix.log" -journal "$prefix.jou" -tclargs $Attempt
    if($LASTEXITCODE){throw 'OOC experiment failed'}
    Set-Content "$($prefix)_exit.txt" '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content "$($prefix)_exit.txt" '1';exit 1
}
