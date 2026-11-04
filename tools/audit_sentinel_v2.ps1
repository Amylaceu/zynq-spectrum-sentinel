#requires -Version 7.0
param([ValidatePattern('^[a-zA-Z0-9_]+$')][string]$Tag='r1')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$projectDir=Join-Path $env:REPO 'build/work/adi_hdl/projects/fmcomms2/sentinel_v2_100m'
$project=Join-Path $projectDir 'sentinel_v2_100m.xpr'
if(-not(Test-Path -LiteralPath $project)){throw "Missing candidate project: $project"}
$running=Get-ChildItem (Join-Path $env:REPO 'logs') -Filter '*_v2_*_exit.txt' |
    Where-Object {(Get-Content -LiteralPath $_.FullName -Raw).Trim() -eq 'RUNNING'}
if($running){throw "Build still running; do not audit same project concurrently: $($running.Name -join ', ')"}
$prefix="Z10_v2_audit_$Tag"
$exitFile=Join-Path $env:REPO "logs/$($prefix)_exit.txt"
if(Test-Path -LiteralPath $exitFile){throw "Preserve previous audit: $exitFile"}
Set-Content -LiteralPath $exitFile -Value 'RUNNING'
$env:SENTINEL_AUDIT_TAG=$Tag
$code=1
try {
    Push-Location $projectDir
    try {
        & (Join-Path $env:XILINX_ROOT 'Vivado/bin/vivado.bat') -mode batch -notrace -source (Join-Path $env:REPO 'build/scripts/audit_sentinel_v2.tcl') -log (Join-Path $env:REPO "logs/$prefix.log") -journal (Join-Path $env:REPO "logs/$prefix.jou")
        if($LASTEXITCODE -ne 0){throw "Vivado audit failed; inspect logs/$prefix.log"}
        $code=0
    } finally {Pop-Location}
} finally {Set-Content -LiteralPath $exitFile -Value "$code"}
if($code){exit $code}
