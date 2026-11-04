param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$exitFile="logs/N4_final_audit_round${Attempt}_exit.txt"
if(Test-Path -LiteralPath $exitFile){throw "Preserve previous audit: $exitFile"}
Set-Content $exitFile 'RUNNING'
try {
    & "$env:XILINX_ROOT/Vivado/bin/vivado.bat" -mode batch -notrace -source build/scripts/audit_sentinel_v1.tcl `
        -log "logs/N4_final_audit_round${Attempt}.log" -journal "logs/N4_final_audit_round${Attempt}.jou"
    if($LASTEXITCODE){throw 'Full-system timing/CDC audit failed'}
    & $env:ZSS_PYTHON tools/accept_sentinel_v1.py
    if($LASTEXITCODE){throw 'Full-system artifact/resource acceptance failed'}
    Set-Content $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content $exitFile '1';exit 1
}
