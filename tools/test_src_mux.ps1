param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$exitFile="logs/N4_src_round${Attempt}_exit.txt"
Set-Content $exitFile 'RUNNING'
try {
    & $env:ZSS_PYTHON tools/export_src_vectors.py
    if($LASTEXITCODE){throw 'Source reference export failed'}
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_src_mux `
        -Srcs @('src/rtl/src_mux/src_mux.v','src/rtl/regs/src_ctrl_regs.v','sim/tb/tb_src_mux.sv') `
        -MemoryFiles @('data/reference/src_mux/n4_sine.hex','data/reference/src_mux/n4_src_input.hex',
            'data/reference/src_mux/n4_src_expected.hex','data/reference/src_mux/n4_src_config.hex')
    & $env:ZSS_PYTHON tools/golden_compare.py --exp data/reference/src_mux/n4_src_expected.hex `
        --got sim/results/n4_src_out.hex --mode exact --report sim/results/n4_src_compare.json
    if($LASTEXITCODE){throw 'Source comparison failed'}
    Set-Content $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content $exitFile '1';exit 1
}
