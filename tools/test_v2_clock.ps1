#requires -Version 7.0
param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$runId="z10_clock_r$Attempt"
$exitFile="logs/Z10_clock_r$($Attempt)_exit.txt"
if(Test-Path -LiteralPath $exitFile){throw 'Preserve previous clock test evidence'}
Set-Content -LiteralPath $exitFile 'RUNNING'
try {
    $vectors="build/work/$runId/vectors"
    & $env:ZSS_PYTHON tools/export_src_vectors.py --clock-hz 100000000 --rate-hz 3840000 --out $vectors
    if($LASTEXITCODE){throw '100 MHz vectors failed'}
    $memories=@(Get-ChildItem "$vectors/*.hex" | ForEach-Object {"$vectors/$($_.Name)"})
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_src_mux -RunId $runId -Defines DSP_100MHZ `
        -Srcs @('src/rtl/src_mux/src_mux.v','src/rtl/regs/src_ctrl_regs.v','sim/tb/tb_src_mux.sv') `
        -MemoryFiles $memories
    & $env:ZSS_PYTHON tools/golden_compare.py --exp "$vectors/n4_src_expected.hex" `
        --got "sim/results/$runId/n4_src_out.hex" --mode exact --report "sim/results/$runId/source_compare.json"
    if($LASTEXITCODE){throw '100 MHz source comparison failed'}
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_perf_mon -RunId $runId -Defines DSP_100MHZ `
        -Srcs @('src/rtl/perf/*.v','src/rtl/regs/perf_ctrl_regs.v','sim/tb/tb_perf_mon.sv')
    & $env:ZSS_PYTHON -m pytest src/ps/tests/test_v2_clock.py src/ps/tests/test_v1.py src/ps/tests/test_audio_y3.py -q
    if($LASTEXITCODE){throw 'Clock-sensitive PS regression failed'}
    Set-Content -LiteralPath $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content -LiteralPath $exitFile '1'
    exit 1
}
