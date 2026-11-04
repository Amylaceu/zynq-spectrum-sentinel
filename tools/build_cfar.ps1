param([ValidateRange(1,3)][int]$Attempt=1,[switch]$PackageOnly)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$kind=if($PackageOnly){'package'}else{'synth'}
$exitFile="logs/N3_${kind}_round${Attempt}_exit.txt"
Set-Content $exitFile 'RUNNING'
try {
    $log="logs/N3_${kind}_round${Attempt}.log"
    if($PackageOnly){
        $script='build/scripts/package_ip.tcl'
        $arguments=@('cfar_core','src/rtl/cfar',"build/work/n3_packaged_ip_round$Attempt")
        $marker='IP_PACKAGE_PASS cfar_core'
    }else{
        $script='build/scripts/synth_module.tcl'
        $arguments=@('cfar_core','src/rtl/cfar','150')
        $marker='MODULE_SYNTHESIS_PASS cfar_core'
    }
    & "$env:XILINX_ROOT/Vivado/bin/vivado.bat" -mode batch -notrace -source $script `
        -log $log -journal "logs/N3_${kind}_round${Attempt}.jou" -tclargs @arguments
    if($LASTEXITCODE -ne 0){throw "CFAR $kind failed"}
    if(-not(Select-String -LiteralPath $log -Pattern $marker -Quiet)){throw 'Missing CFAR completion marker'}
    Set-Content $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content $exitFile '1';exit 1
}
