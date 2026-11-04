param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$exitFile="logs/N4_src_synth_round${Attempt}_exit.txt"
Set-Content $exitFile 'RUNNING'
try {
    & "$env:XILINX_ROOT/Vivado/bin/vivado.bat" -mode batch -notrace `
        -source build/scripts/synth_module.tcl -log "logs/N4_src_synth_round${Attempt}.log" `
        -journal "logs/N4_src_synth_round${Attempt}.jou" -tclargs src_mux src/rtl/src_mux 150
    if($LASTEXITCODE){throw 'Source150MHz synthesis/implementation failed'}
    Set-Content $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content $exitFile '1';exit 1
}
