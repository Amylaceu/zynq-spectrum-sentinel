#requires -Version 7.0
param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$prefix="Z10_v2_clock_ip_r$Attempt"
$exitFile=Join-Path $env:REPO "logs/$($prefix)_exit.txt"
if(Test-Path -LiteralPath $exitFile){throw 'Preserve previous Z10 packaging evidence'}
New-Item -ItemType Directory -Path (Join-Path $env:REPO 'logs') -Force | Out-Null
Set-Content -LiteralPath $exitFile -Value 'RUNNING'
$code=0
try {
    & (Join-Path $env:XILINX_ROOT 'Vivado/bin/vivado.bat') -mode batch -notrace -source (Join-Path $env:REPO 'build/scripts/reclock_v2_ip.tcl') -log (Join-Path $env:REPO "logs/$prefix.log") -journal (Join-Path $env:REPO "logs/$prefix.jou")
    if($LASTEXITCODE -ne 0){throw "IP packaging failed; inspect logs/$prefix.log"}
    if(-not(Select-String -LiteralPath (Join-Path $env:REPO "logs/$prefix.log") -SimpleMatch 'Z10_V2_CLOCK_IP_PACKAGING_PASS' -Quiet)){throw 'Missing v2 IP package completion marker'}
}catch{$_ | Out-String | Write-Output; $code=1}
Set-Content -LiteralPath $exitFile -Value "$code"
if($code){exit $code}
