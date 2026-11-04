param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$log="logs/X1_cluster_ooc_r$Attempt.log"
$exitFile="logs/X1_cluster_ooc_r$($Attempt)_exit.txt"
if ((Test-Path $log) -or (Test-Path $exitFile)) { throw 'Preserve previous evidence' }
Set-Content $exitFile 'RUNNING'
try {
    & "$env:XILINX_ROOT/Vivado/bin/vivado.bat" -mode batch -notrace -source build/scripts/synth_cfar_cluster_x1.tcl -log $log -journal "logs/X1_cluster_ooc_r$Attempt.jou" -tclargs $Attempt
    if($LASTEXITCODE) { throw 'X1 standalone cluster implementation failed' }
    if(-not (Select-String -LiteralPath $log -SimpleMatch 'X1_CLUSTER_OOC_PASS' -Quiet)) { throw 'Missing PASS marker' }
    Set-Content $exitFile '0'
} catch {
    Write-Output ($_ | Out-String)
    Set-Content $exitFile '1'
    exit 1
}
