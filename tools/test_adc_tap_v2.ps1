param([ValidateRange(1,3)][int]$Attempt=1,
      [ValidatePattern('^[a-zA-Z0-9_]+$')][string]$RunId='')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$label=if($RunId){$RunId}else{"round${Attempt}"}
$exitFile="logs/Z10_adc_${label}_exit.txt"
if(Test-Path -LiteralPath $exitFile){throw 'Preserve prior ADC regression evidence'}
$result=if($RunId){"sim/results/$RunId/tb_adc_tap_v2.log"}else{'sim/results/tb_adc_tap_v2.log'}
Set-Content $exitFile 'RUNNING'
try {
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_adc_tap_v2 `
        -Srcs @('src/rtl/adc_tap_v2/adc_tap_v2.v','sim/tb/tb_adc_tap_v2.sv') -IncludeGlbl -RunId $RunId
    if(Select-String -LiteralPath $result -Pattern '^Error:|^ERROR:|^Fatal:|^FATAL:' -Quiet){
        throw 'Simulation assertion/error despite the testbench PASS marker'
    }
    Set-Content $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content $exitFile '1';exit 1
}
