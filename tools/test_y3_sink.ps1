param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$exitFile="logs/Y3_sink_r${Attempt}_exit.txt"
if(Test-Path $exitFile){throw 'Preserve prior attempt'}
$vectors=if($Attempt -eq 3){'build/work/y3_sink_vectors_r3'}else{'build/work/y3_fm_vectors_r3'}
if(-not(Test-Path "$vectors/vectors.json.sha256")){throw 'Require preserved FM r3 vectors'}
Set-Content $exitFile 'RUNNING'
try {
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_audio_sink_y3 -IncludeGlbl `
        -Srcs @('src/rtl/audio_y3/fm_phase_y3.v','src/rtl/audio_y3/fm_audio_filter_y3.v',
            'src/rtl/audio_y3/i2s_tx_y3.v','src/rtl/audio_y3/audio_sink_y3.v',
            'sim/tb/tb_audio_sink_y3.sv') `
        -MemoryFiles @(Get-ChildItem "$vectors/*.hex" | ForEach-Object {$_.FullName.Substring($env:REPO.Length+1)})
    Set-Content $exitFile '0'
} catch { $_ | Out-String | Write-Output;Set-Content $exitFile '1';exit 1 }
