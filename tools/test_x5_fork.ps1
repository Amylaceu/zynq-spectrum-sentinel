param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$exitFile="logs/X5_fork_r${Attempt}_exit.txt"
if(Test-Path $exitFile) { throw 'Preserve prior attempt' }
Set-Content $exitFile 'RUNNING'
try {
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_x5_fork `
        -Srcs @('src/rtl/x5/x5_frontend.v','sim/tb/tb_x5_fork.sv')
    Set-Content $exitFile '0'
} catch { $_ | Out-String | Write-Output;Set-Content $exitFile '1';exit 1 }
