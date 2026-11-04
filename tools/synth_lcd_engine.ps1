param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$exitFile="logs/N4_lcd_synth_round${Attempt}_exit.txt"
Set-Content $exitFile 'RUNNING'
try {
    & "$env:XILINX_ROOT/Vivado/bin/vivado.bat" -mode batch -notrace `
        -source build/scripts/synth_lcd_engine.tcl -log "logs/N4_lcd_synth_round${Attempt}.log" `
        -journal "logs/N4_lcd_synth_round${Attempt}.jou"
    if($LASTEXITCODE){throw 'LCD engine implementation failed'}
    Set-Content $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content $exitFile '1';exit 1
}
