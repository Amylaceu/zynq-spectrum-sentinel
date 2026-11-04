param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$exitFile="logs/Y3_i2s_r${Attempt}_exit.txt"
if(Test-Path $exitFile) { throw 'Preserve prior attempt' }
Set-Content $exitFile 'RUNNING'
try {
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_i2s_tx_y3 `
        -Srcs @('src/rtl/audio_y3/i2s_tx_y3.v','sim/tb/tb_i2s_tx_y3.sv')
    Set-Content $exitFile '0'
} catch { $_ | Out-String | Write-Output;Set-Content $exitFile '1';exit 1 }
