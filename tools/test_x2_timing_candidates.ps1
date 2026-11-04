#requires -Version 7.0
param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$prefix="logs/X2_timing_candidates_r$Attempt"
if(Test-Path "$($prefix)_exit.txt"){throw 'Preserve prior optimization evidence'}
Set-Content "$($prefix)_exit.txt" 'RUNNING'
try {
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_x2_drop_counter -Srcs @(
        'src/rtl/x2_opt/drop_counter_segmented.v','sim/tb/tb_x2_drop_counter.sv')
    Copy-Item sim/results/tb_x2_drop_counter.log "$($prefix)_counter.log"
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_x2_timing_candidates -Srcs @(
        'src/rtl/cfar_x1/cfar_cluster_x1.v','src/rtl/x2_opt/cfar_cluster_timing_x2.v',
        'sim/tb/tb_x2_timing_candidates.sv')
    Copy-Item sim/results/tb_x2_timing_candidates.log "$($prefix)_cluster.log"
    Set-Content "$($prefix)_exit.txt" '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content "$($prefix)_exit.txt" '1'
    exit 1
}
