param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$exitFile="logs/N2_package_round${Attempt}_exit.txt"
Set-Content $exitFile 'RUNNING'
try {
    $log="logs/N2_package_round${Attempt}.log"
    & "$env:XILINX_ROOT/Vivado/bin/vivado.bat" -mode batch -notrace `
        -source build/scripts/package_ip.tcl -log $log -journal "logs/N2_package_round${Attempt}.jou" `
        -tclargs spec_front src/rtl/spectrum "build/work/packaged_ip_round${Attempt}"
    if($LASTEXITCODE -ne 0){throw 'spec_front IP packaging failed'}
    if(-not(Select-String -LiteralPath $log -Pattern 'IP_PACKAGE_PASS spec_front' -Quiet)){
        throw 'Missing package completion marker'
    }
    Set-Content $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content $exitFile '1'
    exit 1
}
