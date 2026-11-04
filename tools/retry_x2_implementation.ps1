#requires -Version 7.0
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$prefix='logs/X2_v1c_implementation_r2'
if(Test-Path "$($prefix)_exit.txt"){throw 'Preserve previous implementation attempt'}
& $env:ZSS_PYTHON tools/freeze_x2_build.py --attempt 2 --verify
if($LASTEXITCODE){throw 'Frozen retry inputs changed'}
Set-Content "$($prefix)_exit.txt" 'RUNNING'
try {
    & "$env:XILINX_ROOT/Vivado/bin/vivado.bat" -mode batch -notrace -source build/scripts/retry_x2_implementation.tcl -log "$prefix.log" -journal "$prefix.jou"
    if($LASTEXITCODE){throw 'Implementation retry failed; preserve report and do not load'}
    & (Join-Path $PSScriptRoot 'collect_hw.ps1') -Proj sentinel_v1c -Tag sentinel_v1c
    Set-Content "$($prefix)_exit.txt" '0'
    & (Join-Path $PSScriptRoot 'audit_sentinel_v1c.ps1') -Attempt 2
    if($LASTEXITCODE){throw 'Final audit failed'}
} catch {
    $_ | Out-String | Write-Output
    Set-Content "$($prefix)_exit.txt" '1'
    exit 1
}
