#requires -Version 7.0
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$prefix='Y3_v2_audio_route_repair_r1'
$exitPath=Join-Path $env:REPO "logs/${prefix}_exit.txt"
if(Test-Path $exitPath){throw 'Preserve prior repair'}
Set-Content $exitPath 'RUNNING'
$code=1
try {
    & $env:ZSS_PYTHON tools/freeze_v2_inputs.py --tag $prefix --power-optimization Off
    if($LASTEXITCODE){throw 'Cannot freeze repair inputs'}
    & (Join-Path $env:XILINX_ROOT 'Vivado/bin/vivado.bat') -mode batch -notrace `
      -source (Join-Path $env:REPO 'build/scripts/repair_v2_audio_routes.tcl') `
      -log (Join-Path $env:REPO "logs/$prefix.log") `
      -journal (Join-Path $env:REPO "logs/$prefix.jou")
    $code=$LASTEXITCODE
    if($code -eq 0){
        & $env:ZSS_PYTHON tools/freeze_v2_inputs.py --tag $prefix --verify --power-optimization Off
        $code=$LASTEXITCODE
    }
} finally {Set-Content $exitPath $code}
exit $code
