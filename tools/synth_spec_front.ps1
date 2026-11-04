param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$exitFile="logs/N2_front_synth_round${Attempt}_exit.txt"
Set-Content $exitFile 'RUNNING'
try {
    $log="logs/N2_front_synth_round${Attempt}.log"
    & "$env:XILINX_ROOT/Vivado/bin/vivado.bat" -mode batch -notrace `
        -source build/scripts/synth_module.tcl -log $log -journal "logs/N2_front_synth_round${Attempt}.jou" `
        -tclargs spec_front src/rtl/spectrum 150
    if($LASTEXITCODE -ne 0){throw 'Full spec_front synthesis/implementation failed'}
    if(-not(Select-String -LiteralPath $log -Pattern 'MODULE_SYNTHESIS_PASS spec_front' -Quiet)){
        throw 'Missing full-front timing acceptance marker'
    }
    Set-Content $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content $exitFile '1'
    exit 1
}
