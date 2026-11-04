param([switch]$Smoke)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$python=Join-Path $env:REPO '.venv/Scripts/python.exe'
$tag=if($Smoke){'P2.9_smoke'}else{'P2.9'}
$data=if($Smoke){'build/work/amc_smoke'}else{'data/synthetic/amc_v1'}
$weights=if($Smoke){'build/work/amc_smoke_weights'}else{'src/ps/models/weights'}
$count=if($Smoke){10}else{2000}
$epochs=if($Smoke){1}else{40}
$workers=if($Smoke){2}else{4}
$threads=if($Smoke){4}else{8}
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$exitFile=Join-Path $env:REPO "logs/${tag}_exit.txt"
$master=Join-Path $env:REPO "logs/${tag}.log"
'RUNNING' | Set-Content -LiteralPath $exitFile
"$(Get-Date -Format o) start smoke=$Smoke" | Set-Content -LiteralPath $master
try {
    if(-not(Test-Path (Join-Path $data 'manifest.json'))){
        & $python -u -m src.ps.models.make_dataset --out $data --per-cell $count --workers $workers *> "logs/${tag}_dataset.log"
        if($LASTEXITCODE -ne 0){throw "Dataset failed; see logs/${tag}_dataset.log"}
    }
    "$(Get-Date -Format o) dataset complete; training fusion network" | Add-Content $master
    $trainArgs=@('-u','-m','src.ps.models.amc_train','--data',$data,'--out',$weights,'--epochs',"$epochs",'--bs','256','--threads',"$threads")
    if($Smoke){$trainArgs+='--smoke'}
    & $python @trainArgs *> "logs/${tag}_train.log"
    if($LASTEXITCODE -ne 0){throw "Fusion training/acceptance failed; see logs/${tag}_train.log"}
    if(-not $Smoke){
        "$(Get-Date -Format o) fusion passed FP32 target; training CNN-only baseline" | Add-Content $master
        & $python @trainArgs --cnn-only *> "logs/${tag}_cnn_train.log"
        if($LASTEXITCODE -ne 0){throw "CNN-only training failed; see logs/${tag}_cnn_train.log"}
    }
    "$(Get-Date -Format o) training finished; INT8 export/evaluation still required" | Add-Content $master
    '0' | Set-Content $exitFile
} catch {
    "$(Get-Date -Format o) FAIL: $($_.Exception.Message)" | Add-Content $master
    '1' | Set-Content $exitFile
    exit 1
}
