param([ValidateRange(2,3)][int]$Round=2)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$python=Join-Path $env:REPO '.venv/Scripts/python.exe'
$out="build/work/amc_round$Round"
$log="logs/P2.9_round${Round}_train.log"
$exitFile="logs/P2.9_round${Round}_exit.txt"
if(Test-Path (Join-Path $out 'amc_v1_fp32.pt')){throw 'Round checkpoint already exists; do not overwrite'}
'RUNNING' | Set-Content $exitFile
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
try {
    $extra=if($Round -eq 2){@('--input-mode','differential')}else{@('--input-mode','raw','--curriculum-epochs','10','--phase-augment')}
    & $python -u -m src.ps.models.amc_train --data data/synthetic/amc_v1 --out $out --epochs 40 --bs 256 --threads 8 @extra *> $log
    if($LASTEXITCODE -ne 0){throw "Training/acceptance failed; see $log"}
    '0' | Set-Content $exitFile
} catch {
    Add-Content $log "ROUND_FAILED: $($_.Exception.Message)"
    '1' | Set-Content $exitFile
    exit 1
}
