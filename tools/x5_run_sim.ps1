param([ValidateRange(1,3)][int]$Round=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
Set-Location $env:REPO
& $env:ZSS_PYTHON tools/x5_vectors.py
if($LASTEXITCODE){throw 'X5 vector generation failed'}
$vec='build/work/x5_vectors/'
$roms=@('src/rtl/pfb/x5_pfb_coeff.hex','src/rtl/nco_capture/x5_nco_sine.hex')
$libs=@('xfft_v9_1_15','xbip_utils_v3_0_15','axi_utils_v2_0_11','c_reg_fd_v12_0_11',
    'xbip_dsp48_wrapper_v3_0_7','xbip_pipe_v3_0_11','c_addsub_v12_0_21',
    'c_shift_ram_v12_0_20','mult_gen_v12_0_24','floating_point_v7_1_21','cmpy_v6_0_27')
& ./sim/scripts/run_xsim.ps1 -Top tb_x5_nco_capture `
    -Srcs @('src/rtl/nco_capture/nco_capture.v','sim/tb/tb_x5_nco_capture.sv') `
    -MemoryFiles @($roms[1],($vec+'x5_nco_input.hex'),($vec+'x5_nco_expected.hex'))
Copy-Item sim/results/tb_x5_nco_capture.log "logs/X5_nco_round$Round.log"
& ./sim/scripts/run_xsim.ps1 -Top tb_x5_pfb `
    -Srcs @('src/rtl/pfb/pfb_os2.v','src/rtl/nco_capture/nco_capture.v','sim/tb/tb_x5_pfb.sv') `
    -VhdlFiles @('build/work/x5_fft/x5_fft.gen/sources_1/ip/pfb_fft16/sim/pfb_fft16.vhd') `
    -Libraries $libs -IncludeGlbl `
    -MemoryFiles @($roms[0],$roms[1],($vec+'x5_input.hex'),($vec+'x5_pfb_expected.hex'),($vec+'x5_chain_expected.hex'))
Copy-Item sim/results/tb_x5_pfb.log "logs/X5_pfb_round$Round.log"
Write-Output "X5_SIM_ROUND_${Round}_PASS"
