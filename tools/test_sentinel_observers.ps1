param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$exitFile="logs/N4_observers_round${Attempt}_exit.txt"
Set-Content $exitFile 'RUNNING'
try {
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_sentinel_observers `
        -Srcs @('src/rtl/common/sentinel_capture.v','src/rtl/common/sentinel_events.v','sim/tb/tb_sentinel_observers.sv')
    Set-Content $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content $exitFile '1';exit 1
}
