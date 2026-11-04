#requires -Version 7.0
param([ValidateRange(1,3)][int]$Attempt=1,[switch]$ValidateOnly,
      [switch]$ImplOnly,[switch]$ContinueBuild,[string]$ValidatedLog='',
      [string]$ReferenceCheckpoint='',
      [ValidatePattern('^[a-zA-Z0-9_]*$')][string]$ResumeId='',
      [switch]$RefreshAdc,[switch]$RefreshClocks,
      [ValidateSet('Z10','T5')][string]$Stage='Z10',
      [ValidateSet('On','Off')][string]$PowerOptimization='On')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$active=Get-ChildItem logs -Filter '*_v2_*_exit.txt' -ErrorAction SilentlyContinue | Where-Object {
    (Get-Content -LiteralPath $_.FullName -Raw).Trim() -eq 'RUNNING'
}
if($active){throw "Another v2 build or audit is running: $($active.Name -join ', ')"}
if(([int]$ValidateOnly.IsPresent+[int]$ImplOnly.IsPresent+[int]$ContinueBuild.IsPresent) -gt 1){throw 'Choose one build mode'}
if($RefreshClocks -and -not $ContinueBuild){throw 'RefreshClocks requires ContinueBuild'}
if($Stage -eq 'T5' -and -not $ImplOnly){throw 'T5 requires ImplOnly and the retained synthesis'}
if($PowerOptimization -eq 'Off' -and ($Stage -ne 'T5' -or -not $ImplOnly)){
    throw 'The power-off comparison is a distinct T5 implementation, not a Z10 retry'
}
if(-not(Test-Path build/work/v2_cfar_packaged_ip/cfar_core_v2/component.xml)){
    throw 'Run tools/package_cfar_v2.ps1 first'
}
foreach($ip in @('src_mux','spec_front','perf_mon','lcd8080_engine_x5')){
    if(-not(Test-Path "build/work/v2_clock_packaged_ip/$ip/component.xml")){
        throw "Run tools/package_v2_clock_ip.ps1 first: $ip missing"
    }
}
if(-not(Test-Path build/work/x5_packaged_ip/lcd8080_engine_x5/component.xml)){
    throw 'X5 LCD package is missing'
}
$tag=if($ValidateOnly){'validate'}elseif($ImplOnly){'impl_only'}elseif($ContinueBuild){'continue'}else{'full'}
$prefix="$($Stage)_v2_$($tag)_r$Attempt"
if($ResumeId){
    if(-not($ContinueBuild -or $ImplOnly)){throw 'ResumeId is only for an interrupted existing build'}
    $prefix+="_$ResumeId"
}
$exitFile="logs/$($prefix)_exit.txt"
if(Test-Path -LiteralPath $exitFile){throw 'Preserve previous Z10 attempt evidence'}
$projectDir=Join-Path $env:REPO 'build/work/adi_hdl/projects/fmcomms2/sentinel_v2_100m'
$projectFile=Join-Path $projectDir 'sentinel_v2_100m.xpr'
if($ImplOnly -or $ContinueBuild){
    if(-not(Test-Path -LiteralPath $projectFile)){throw 'No existing v2 synthesis to reuse'}
    if($ContinueBuild){
        if(-not $ValidatedLog -or -not(Test-Path -LiteralPath $ValidatedLog)){
            throw 'ContinueBuild requires a successful ValidateOnly log'
        }
        if(-not(Select-String -LiteralPath $ValidatedLog -SimpleMatch 'SENTINEL_BD_VALIDATION_PASS' -Quiet)){
            throw 'Referenced validation log has no completion marker'
        }
    }
    if($ReferenceCheckpoint -and -not(Test-Path -LiteralPath $ReferenceCheckpoint)){
        throw 'Reference checkpoint not found'
    }
}else{
    if(Test-Path -LiteralPath $projectFile){throw 'Fresh v2 project already exists; use ImplOnly or preserve it before a new synthesis'}
    & (Join-Path $PSScriptRoot 'sync_hw.ps1') -Proj sentinel_v2_100m | Out-Host
}
New-Item -ItemType Directory -Path logs -Force | Out-Null
Set-Content -LiteralPath $exitFile -Value 'RUNNING'
$code=0
$locationPushed=$false
try {
    $env:SENTINEL_POWER_OPTIMIZATION=$PowerOptimization
    & $env:ZSS_PYTHON (Join-Path $PSScriptRoot 'freeze_v2_inputs.py') --tag $prefix --power-optimization $PowerOptimization
    if($LASTEXITCODE -ne 0){throw 'Could not freeze v2 inputs'}
    Push-Location $projectDir
    $locationPushed=$true
    $env:ADI_MAX_OOC_JOBS='6'
    $env:ADI_MAX_THREADS='8'
    $env:ADI_AUTOFIX_MAX_ATTEMPTS='2'
    $env:SENTINEL_VALIDATE_ONLY=if($ValidateOnly){'1'}else{'0'}
    $env:SENTINEL_BUILD_TAG=$prefix
    $env:SENTINEL_REFRESH_ADC=if($RefreshAdc){'1'}else{'0'}
    $env:SENTINEL_REFRESH_CLOCKS=if($RefreshClocks){'1'}else{'0'}
    $env:SENTINEL_REFERENCE_DCP=$ReferenceCheckpoint
    $env:SENTINEL_CONTINUE_BUILD=if($ContinueBuild){'1'}else{'0'}
    $env:SENTINEL_IMPL_ONLY=if($ImplOnly){'1'}else{'0'}
    $script=if($ImplOnly -or $ContinueBuild){Join-Path $env:REPO 'build/scripts/resume_sentinel_v2.tcl'}else{'system_project.tcl'}
    & (Join-Path $env:XILINX_ROOT 'Vivado/bin/vivado.bat') -mode batch -notrace -source $script -log (Join-Path $env:REPO "logs/$prefix.log") -journal (Join-Path $env:REPO "logs/$prefix.jou")
    if($LASTEXITCODE -ne 0){throw "Vivado Z10 $tag failed; inspect logs/$prefix.log"}
    & $env:ZSS_PYTHON (Join-Path $PSScriptRoot 'freeze_v2_inputs.py') --tag $prefix --verify --power-optimization $PowerOptimization
    if($LASTEXITCODE -ne 0){throw 'v2 inputs changed during implementation'}
}catch{$_ | Out-String | Write-Output; $code=1}finally{if($locationPushed){Pop-Location}}
Set-Content -LiteralPath $exitFile -Value "$code"
if($code){exit $code}
