#requires -Version 7.0
param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$prefix="logs/X2_chain_r$Attempt"
if(Test-Path "$($prefix)_exit.txt"){throw 'Preserve prior attempt'}
Set-Content "$($prefix)_exit.txt" 'RUNNING'
try {
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_adc_tap_x2 `
        -Srcs @('src/rtl/x2/adc_tap_x2.v','sim/tb/tb_adc_tap_x2.sv') -IncludeGlbl
    Copy-Item sim/results/tb_adc_tap_x2.log "$($prefix)_adc.log"
    $memories=@('bh4','hann','rect' | ForEach-Object {"data/reference/spectrum/spec_window_$_.hex"})
    $memories+=@('data/reference/spectrum/spec_log_mantissa.hex',
        'data/reference/spectrum/in_axis32.hex','data/reference/spectrum/exp_welch.hex','data/reference/spectrum/n2_display_expected.hex')
    $sources=@('src/rtl/spectrum/*.v','src/rtl/x2/*.v','src/rtl/cfar_x1/*.v','src/rtl/cfar/cfar_occupancy.v',
        'src/rtl/regs/spec_ctrl_regs.v','src/rtl/common/axis_fork2.v','src/rtl/common/axis_broadcast2.v',
        'src/rtl/lcd/lcd_snapshot.v','sim/tb/tb_sentinel_chain_x2.sv')
    $vhdl='build/work/spec_front/spec_front.gen/sources_1/ip/spec_fft_2048/sim/spec_fft_2048.vhd'
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_sentinel_chain_x2 -Srcs $sources -VhdlFiles @($vhdl) -IncludeGlbl `
        -Libraries @('xfft_v9_1_15','xbip_utils_v3_0_15','axi_utils_v2_0_11','c_reg_fd_v12_0_11',
          'xbip_dsp48_wrapper_v3_0_7','xbip_pipe_v3_0_11','c_addsub_v12_0_21',
          'c_shift_ram_v12_0_20','mult_gen_v12_0_24','floating_point_v7_1_21','cmpy_v6_0_27') -MemoryFiles $memories
    Copy-Item sim/results/tb_sentinel_chain_x2.log "$($prefix)_chain.log"
    Set-Content "$($prefix)_exit.txt" '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content "$($prefix)_exit.txt" '1';exit 1
}
