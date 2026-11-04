param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$exitFile="logs/N2_stages_round${Attempt}_exit.txt"
Set-Content $exitFile 'RUNNING'
try {
    & $env:ZSS_PYTHON tools/export_spec_stage_vectors.py
    if($LASTEXITCODE){throw 'Stage vectors failed'}
    $sources=@('window','power','welch','db' | ForEach-Object {"src/rtl/spectrum/spec_$_.v"})
    $memories=@('bh4','hann','rect' | ForEach-Object {"data/reference/spectrum/spec_window_$_.hex"})
    $memories+=@('data/reference/spectrum/spec_log_mantissa.hex','data/reference/spectrum/n2_stages_in.hex','data/reference/spectrum/n2_stages_expected.hex')
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_spec_stages -Srcs ($sources+@('sim/tb/tb_spec_stages.sv')) -MemoryFiles $memories
    Set-Content $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content $exitFile '1'
    exit 1
}
