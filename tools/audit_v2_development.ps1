#requires -Version 7.0
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$tag='development_r2'
$prefix='Y3_v2_development_audit_r2'
$exitPath=Join-Path $env:REPO "logs/${prefix}_exit.txt"
if(Test-Path $exitPath){throw 'Preserve prior development audit'}
$env:SENTINEL_AUDIT_TAG=$tag
Set-Content $exitPath 'RUNNING'
$code=1
try {
    & (Join-Path $env:XILINX_ROOT 'Vivado/bin/vivado.bat') -mode batch -notrace `
      -source (Join-Path $env:REPO 'build/scripts/audit_v2_development.tcl') `
      -log (Join-Path $env:REPO "logs/$prefix.log") `
      -journal (Join-Path $env:REPO "logs/$prefix.jou")
    $code=$LASTEXITCODE
} finally {Set-Content $exitPath $code}
exit $code
