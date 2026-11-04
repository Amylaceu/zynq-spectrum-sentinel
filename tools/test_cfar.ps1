param([ValidateRange(1,3)][int]$Attempt=1,[switch]$FinalVerification)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$suffix=if($FinalVerification){'_final'}else{''}
$exitFile="logs/N3_sim_round${Attempt}${suffix}_exit.txt"
Set-Content $exitFile 'RUNNING'
try {
    & $env:ZSS_PYTHON tools/export_cfar_rtl_vectors.py
    if($LASTEXITCODE){throw 'CFAR reference generation failed'}
    $sources=@('src/rtl/cfar/*.v','src/rtl/regs/cfar_ctrl_regs.v','src/rtl/common/axis_broadcast2.v','sim/tb/tb_cfar_core.sv')
    $memories=@(Get-ChildItem data/reference/cfar/n3/*.hex | ForEach-Object {"data/reference/cfar/n3/$($_.Name)"})
    $memories+='data/reference/spectrum/spec_log_mantissa.hex'
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_cfar_core -Srcs $sources -MemoryFiles $memories
    foreach($name in @('threshold','hit','db','occupancy','targets_words')){
        $actual=if($name -eq 'targets_words'){'targets'}else{$name}
        & $env:ZSS_PYTHON tools/golden_compare.py --exp "data/reference/cfar/n3/$name.hex" `
            --got "sim/results/cfar_${actual}_out.hex" --mode exact --report "sim/results/cfar_${actual}_compare.json"
        if($LASTEXITCODE){throw "CFAR comparison failed $name"}
    }
    Set-Content $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content $exitFile '1';exit 1
}
