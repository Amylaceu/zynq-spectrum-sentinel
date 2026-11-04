param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$exitFile="logs/Y3_fm_r${Attempt}_exit.txt"
$vectors="build/work/y3_fm_vectors_r$Attempt"
if(Test-Path $exitFile){throw 'Preserve prior attempt'}
Set-Content $exitFile 'RUNNING'
try {
    & $env:ZSS_PYTHON tools/gen_y3_fm_vectors.py --out $vectors
    if($LASTEXITCODE){throw 'FM golden generation failed'}
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_fm_y3 `
        -Srcs @('src/rtl/audio_y3/fm_phase_y3.v','src/rtl/audio_y3/fm_audio_filter_y3.v','sim/tb/tb_fm_y3.sv') `
        -MemoryFiles @(Get-ChildItem "$vectors/*.hex" | ForEach-Object {$_.FullName.Substring($env:REPO.Length+1)})
    Set-Content $exitFile '0'
} catch { $_ | Out-String | Write-Output;Set-Content $exitFile '1';exit 1 }
