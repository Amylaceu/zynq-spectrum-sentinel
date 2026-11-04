#requires -Version 7.0
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$prefix='Y3_v2_audio_early_r2b'
$exitPath=Join-Path $env:REPO ('logs/{0}_exit.txt' -f $prefix)
if(Test-Path $exitPath){throw 'Preserve prior audio-early audit'}
Set-Content $exitPath 'RUNNING'
$code=1
try {
    $arguments=@(
      '-mode','batch','-notrace',
      '-source',(Join-Path $env:REPO 'build/scripts/inspect_v2_audio_early_r2.tcl'),
      '-log',(Join-Path $env:REPO ('logs/{0}.log' -f $prefix)),
      '-journal',(Join-Path $env:REPO ('logs/{0}.jou' -f $prefix))
    )
    & (Join-Path $env:XILINX_ROOT 'Vivado/bin/vivado.bat') @arguments
    $code=$LASTEXITCODE
} finally {Set-Content $exitPath $code}
exit $code
