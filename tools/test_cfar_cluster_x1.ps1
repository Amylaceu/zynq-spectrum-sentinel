param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$vectorDir="data/reference/cfar/x1_r$Attempt"
$log="logs/X1_cluster_sim_r$Attempt.log"
$exitFile="logs/X1_cluster_sim_r$($Attempt)_exit.txt"
if ((Test-Path $log) -or (Test-Path $exitFile) -or (Test-Path $vectorDir)) {
    throw 'Preserve X1 evidence; choose next Attempt'
}
Set-Content $exitFile 'RUNNING'
Start-Transcript -Path $log | Out-Null
try {
    & $env:ZSS_PYTHON tools/export_cfar_x1_vectors.py --out $vectorDir
    if($LASTEXITCODE) { throw 'X1 vector generation failed' }
    $memories=@(Get-ChildItem "$vectorDir/*.hex" | ForEach-Object {"$vectorDir/$($_.Name)"})
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_cfar_cluster_x1 -Srcs @(
        'src/rtl/cfar_x1/cfar_cluster_x1.v','sim/tb/tb_cfar_cluster_x1.sv'
    ) -MemoryFiles $memories
    Copy-Item sim/results/tb_cfar_cluster_x1.log "logs/X1_cluster_xsim_r$Attempt.log"
    Copy-Item sim/results/x1_cluster_targets_out.hex "logs/X1_cluster_targets_r$Attempt.hex"
    Set-Content $exitFile '0'
} catch {
    Write-Output ($_ | Out-String)
    Set-Content $exitFile '1'
    exit 1
} finally { Stop-Transcript | Out-Null }
