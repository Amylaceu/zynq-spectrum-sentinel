param([ValidateRange(1,3)][int]$Attempt=1)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$exitFile="logs/N2_front_round${Attempt}_exit.txt"
Set-Content $exitFile 'RUNNING'
try {
    & $env:ZSS_PYTHON tools/export_spec_stage_vectors.py
    if($LASTEXITCODE){throw 'Display reference generation failed'}
    $memories=@('bh4','hann','rect' | ForEach-Object {"data/reference/spectrum/spec_window_$_.hex"})
    $memories+=@('spec_log_mantissa.hex','in_axis32.hex','exp_fft.hex','exp_power_shifted.hex','exp_welch.hex','exp_db.hex','n2_display_expected.hex' | ForEach-Object {"data/reference/spectrum/$_"})
    & "$env:REPO/sim/scripts/run_xsim.ps1" -Top tb_spec_front -Srcs (Get-Content sim/tb/tb_spec_front.files) `
        -VhdlFiles @('build/work/spec_front/spec_front.gen/sources_1/ip/spec_fft_2048/sim/spec_fft_2048.vhd') `
        -Libraries @('xfft_v9_1_15','xbip_utils_v3_0_15','axi_utils_v2_0_11','c_reg_fd_v12_0_11',
          'xbip_dsp48_wrapper_v3_0_7','xbip_pipe_v3_0_11','c_addsub_v12_0_21',
          'c_shift_ram_v12_0_20','mult_gen_v12_0_24','floating_point_v7_1_21','cmpy_v6_0_27') `
        -MemoryFiles $memories
    $checks=@(
        @('fft','exp_fft.hex',24),@('power','exp_power_shifted.hex',0),
        @('avg','exp_welch.hex',0),@('db','exp_db.hex',16),@('display','n2_display_expected.hex',16))
    foreach($check in $checks){
        $arguments=@('--exp',"data/reference/spectrum/$($check[1])",'--got',"sim/results/spec_front_$($check[0])_out.hex",'--mode','exact','--report',"sim/results/spec_front_$($check[0])_compare.json")
        if($check[2]){$arguments+=@('--bits',$check[2])}
        & $env:ZSS_PYTHON tools/golden_compare.py @arguments
        if($LASTEXITCODE){throw "Full pipeline comparison failed: $($check[0])"}
    }
    Set-Content $exitFile '0'
} catch {
    $_ | Out-String | Write-Output
    Set-Content $exitFile '1'
    exit 1
}
