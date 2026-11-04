param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$exitFile=Join-Path $env:REPO "logs/N2_fft_round${Attempt}_exit.txt"
Set-Content $exitFile 'RUNNING'
try {
    & (Join-Path $env:XILINX_ROOT 'Vivado/bin/vivado.bat') -mode batch -notrace `
        -source (Join-Path $env:REPO 'build/scripts/create_spec_fft.tcl') `
        -log (Join-Path $env:REPO "logs/N2_fft_round${Attempt}.log") `
        -journal (Join-Path $env:REPO "logs/N2_fft_round${Attempt}.jou")
    if($LASTEXITCODE -ne 0){throw "Vivado failed: $LASTEXITCODE"}
    if(-not(Select-String -LiteralPath "logs/N2_fft_round${Attempt}.log" -Pattern 'N2_FFT_IP_GENERATION_PASS' -Quiet)){
        throw 'Missing FFT generation completion marker'
    }
    Set-Content $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content $exitFile '1'
    exit 1
}
