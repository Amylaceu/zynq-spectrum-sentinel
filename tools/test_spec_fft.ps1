param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$exitFile=Join-Path $env:REPO "logs/N2_fft_sim_round${Attempt}_exit.txt"
Set-Content $exitFile 'RUNNING'
try {
    $roms=@('bh4','hann','rect' | ForEach-Object {"data/reference/spectrum/spec_window_$_.hex"})
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_spec_fft `
        -Srcs @('src/rtl/spectrum/spec_window.v','sim/tb/tb_spec_fft.sv') `
        -VhdlFiles @('build/work/spec_front/spec_front.gen/sources_1/ip/spec_fft_2048/sim/spec_fft_2048.vhd') `
        -Libraries @('xfft_v9_1_15','xbip_utils_v3_0_15','axi_utils_v2_0_11','c_reg_fd_v12_0_11',
          'xbip_dsp48_wrapper_v3_0_7','xbip_pipe_v3_0_11','c_addsub_v12_0_21',
          'c_shift_ram_v12_0_20','mult_gen_v12_0_24','floating_point_v7_1_21','cmpy_v6_0_27') `
        -MemoryFiles ($roms+@('data/reference/spectrum/in_axis32.hex','data/reference/spectrum/exp_fft.hex'))
    & $env:ZSS_PYTHON "$env:REPO/tools/golden_compare.py" --exp data/reference/spectrum/exp_fft.hex `
        --got sim/results/spec_fft_out.hex --mode exact --bits 24 --report sim/results/spec_fft_compare.json
    if($LASTEXITCODE -ne 0){throw 'FFT complete-vector comparison failed'}
    Set-Content $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content $exitFile '1'
    exit 1
}
