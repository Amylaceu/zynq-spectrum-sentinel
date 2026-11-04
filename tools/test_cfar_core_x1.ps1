param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
if(-not(Test-Path sim/tb/tb_cfar_core_x1.sv)) { throw 'Missing X1 integrated testbench; prepare sources first' }
$vectorDir="data/reference/cfar/x1_core_r$Attempt"
$log="logs/X1_core_sim_r$Attempt.log"
$exitFile="logs/X1_core_sim_r$($Attempt)_exit.txt"
if((Test-Path $log) -or (Test-Path $exitFile) -or (Test-Path $vectorDir)) { throw 'Preserve evidence; use next attempt' }
Set-Content $exitFile 'RUNNING'
Start-Transcript -Path $log | Out-Null
try {
    & $env:ZSS_PYTHON tools/export_cfar_x1_core_vectors.py --out $vectorDir
    if($LASTEXITCODE) { throw 'X1 core vector generation failed' }
    $memories=@(Get-ChildItem "$vectorDir/*.hex" | ForEach-Object {"$vectorDir/$($_.Name)"})
    $memories+='data/reference/spectrum/spec_log_mantissa.hex'
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_cfar_core_x1 -Srcs @(
        'src/rtl/cfar_x1/*.v','src/rtl/cfar/cfar_occupancy.v',
        'src/rtl/common/axis_broadcast2.v','sim/tb/tb_cfar_core_x1.sv'
    ) -MemoryFiles $memories
    Copy-Item sim/results/tb_cfar_core_x1.log "logs/X1_core_xsim_r$Attempt.log"
    foreach($name in @('threshold','hit','db','occupancy','targets','stats')) {
        Copy-Item "sim/results/x1_core_$($name)_out.hex" "logs/X1_core_$($name)_r$Attempt.hex"
    }
    Set-Content $exitFile '0'
} catch {
    Write-Output ($_ | Out-String)
    Set-Content $exitFile '1'
    exit 1
} finally { Stop-Transcript | Out-Null }
