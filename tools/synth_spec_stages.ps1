param(
    [ValidateRange(1,3)][int]$Attempt=1,
    [ValidateSet('spec_window','spec_power','spec_welch','spec_db')]
    [string[]]$Modules=@('spec_window','spec_power','spec_welch','spec_db')
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$exitFile="logs/N2_modules_round${Attempt}_exit.txt"
try {
    foreach($module in $Modules){
        Set-Content $exitFile "RUNNING:$module"
        $log="logs/N2_${module}_synth_round${Attempt}.log"
        & "$env:XILINX_ROOT/Vivado/bin/vivado.bat" -mode batch -notrace `
            -source build/scripts/synth_module.tcl `
            -log $log -journal "logs/N2_${module}_synth_round${Attempt}.jou" `
            -tclargs $module src/rtl/spectrum 150
        if($LASTEXITCODE -ne 0){throw "Synthesis failed for $module"}
        if(-not(Select-String -LiteralPath $log -Pattern "MODULE_SYNTHESIS_PASS $module" -Quiet)){
            throw "Missing synthesis acceptance marker for $module"
        }
    }
    Set-Content $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content $exitFile "1:$module"
    exit 1
}
