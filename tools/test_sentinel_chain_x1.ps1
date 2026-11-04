#requires -Version 7.0
param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$prefix="logs/X1_chain_r$Attempt"
if(Test-Path "$($prefix)_exit.txt"){throw 'Preserve prior attempt'}
Set-Content "$($prefix)_exit.txt" 'RUNNING'
try {
    $memories=@('bh4','hann','rect' | ForEach-Object {"data/reference/spectrum/spec_window_$_.hex"})
    $memories+=@('spec_log_mantissa.hex','in_axis32.hex','exp_fft.hex','exp_power_shifted.hex','exp_welch.hex','exp_db.hex','n2_display_expected.hex' | ForEach-Object {"data/reference/spectrum/$_"})
    $sources=@('src/rtl/spectrum/*.v','src/rtl/cfar_x1/*.v','src/rtl/cfar/cfar_occupancy.v',
        'src/rtl/regs/spec_ctrl_regs.v','src/rtl/common/axis_fork2.v','src/rtl/common/axis_broadcast2.v',
        'src/rtl/lcd/lcd_snapshot.v','sim/tb/tb_sentinel_chain_x1.sv')
    $vhdl='build/work/spec_front/spec_front.gen/sources_1/ip/spec_fft_2048/sim/spec_fft_2048.vhd'
    $inputs=@($memories)+@($sources)+@($vhdl)
    $hashes=@{}
    foreach($pattern in $inputs){
        foreach($file in Get-Item $pattern){$hashes[[IO.Path]::GetRelativePath($env:REPO,$file.FullName).Replace([char]92,[char]47)]=(Get-FileHash $file.FullName).Hash.ToLowerInvariant()}
    }
    $hashes | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 "$($prefix)_inputs.json"
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_sentinel_chain_x1 -Srcs $sources -VhdlFiles @($vhdl) `
        -Libraries @('xfft_v9_1_15','xbip_utils_v3_0_15','axi_utils_v2_0_11','c_reg_fd_v12_0_11',
          'xbip_dsp48_wrapper_v3_0_7','xbip_pipe_v3_0_11','c_addsub_v12_0_21',
          'c_shift_ram_v12_0_20','mult_gen_v12_0_24','floating_point_v7_1_21','cmpy_v6_0_27') -MemoryFiles $memories
    Copy-Item sim/results/tb_sentinel_chain_x1.log "$($prefix)_xsim.log"
    & $env:ZSS_PYTHON tools/analyze_sentinel_chain_x1.py --attempt $Attempt
    if($LASTEXITCODE){throw 'X1 chain evidence verification failed'}
    Set-Content "$($prefix)_exit.txt" '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content "$($prefix)_exit.txt" '1'
    exit 1
}
