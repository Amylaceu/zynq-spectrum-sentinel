#requires -Version 7.0
# Inspect existing DCPs only. This never resets or launches implementation.
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$prefix='Z10_power_inspection_r1'
$exitFile=Join-Path $env:REPO "logs/$($prefix)_exit.txt"
if(Test-Path -LiteralPath $exitFile){throw "Preserve prior inspection: $exitFile"}
$running=Get-ChildItem logs -Filter '*_v2_*_exit.txt' | Where-Object {
    (Get-Content -LiteralPath $_.FullName -Raw).Trim() -eq 'RUNNING'
}
if($running){throw 'Wait for the current candidate build/audit to finish'}
Set-Content -LiteralPath $exitFile -Value 'RUNNING'
$code=1
try {
    & (Join-Path $env:XILINX_ROOT 'Vivado/bin/vivado.bat') -mode batch -notrace `
        -source (Join-Path $env:REPO 'build/scripts/inspect_z10_power.tcl') `
        -log (Join-Path $env:REPO "logs/$prefix.log") `
        -journal (Join-Path $env:REPO "logs/$prefix.jou")
    if($LASTEXITCODE -ne 0){throw "Checkpoint inspection failed: logs/$prefix.log"}
    $code=0
} finally {Set-Content -LiteralPath $exitFile -Value "$code"}
exit $code
