param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$exitFile="logs/N4_adc_round${Attempt}_exit.txt"
Set-Content $exitFile 'RUNNING'
try {
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_adc_tap `
        -Srcs @('src/rtl/adc_tap/adc_tap.v','sim/tb/tb_adc_tap.sv') -IncludeGlbl
    Set-Content $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content $exitFile '1';exit 1
}
