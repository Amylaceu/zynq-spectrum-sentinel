# Independent audio bus. FMC IIC at 0x41620000 remains untouched.
ad_ip_instance clk_wiz audio_clock [list PRIM_SOURCE No_buffer PRIM_IN_FREQ 50.000 \
    CLKOUT1_REQUESTED_OUT_FREQ 12.288 USE_RESET true RESET_TYPE ACTIVE_LOW USE_LOCKED true \
    OVERRIDE_MMCM true MMCM_DIVCLK_DIVIDE 3 MMCM_CLKFBOUT_MULT_F 56.125 \
    MMCM_CLKOUT0_DIVIDE_F 76.125]
n4_connect lcd_clk audio_clock/clk_in1
n4_connect sys_ps7/FCLK_RESET0_N audio_clock/resetn
ad_ip_instance proc_sys_reset audio_rstgen [list C_EXT_RST_WIDTH 1]
n4_connect audio_clock/clk_out1 audio_rstgen/slowest_sync_clk
n4_connect sys_ps7/FCLK_RESET0_N audio_rstgen/ext_reset_in
n4_connect audio_clock/locked audio_rstgen/dcm_locked
n4_connect audio_clock/clk_out1 x5_frontend_0/audio_mclk
n4_connect audio_rstgen/peripheral_aresetn x5_frontend_0/audio_mresetn
foreach port {aud_mclk aud_bclk aud_lrc aud_dacdat audio_drive} {create_bd_port -dir O $port}
n4_connect audio_clock/clk_out1 aud_mclk
foreach port {aud_bclk aud_lrc aud_dacdat} {n4_connect x5_frontend_0/$port $port}
n4_connect x5_frontend_0/audio_drive audio_drive

create_bd_intf_port -mode Master -vlnv xilinx.com:interface:iic_rtl:1.0 audio_iic
ad_ip_instance axi_iic axi_iic_audio [list IIC_FREQ_KHZ 100]
n4_connect audio_iic axi_iic_audio/iic
ad_cpu_interconnect 0x41630000 axi_iic_audio
# PYNQ XIic uses polling; deliberately no interrupt shared with the RF DMA.

ad_ip_instance axi_gpio y3_audio_ctrl [list C_GPIO_WIDTH 32 C_ALL_OUTPUTS 1 \
    C_DOUT_DEFAULT 0x00000000 C_IS_DUAL 1 C_GPIO2_WIDTH 32 C_ALL_OUTPUTS_2 1 C_DOUT_DEFAULT_2 0x00000000]
foreach inst {y3_audio_state y3_audio_counts} {
    ad_ip_instance axi_gpio $inst [list C_GPIO_WIDTH 32 C_ALL_INPUTS 1 \
        C_IS_DUAL 1 C_GPIO2_WIDTH 32 C_ALL_INPUTS_2 1]
}
foreach {inst base} {y3_audio_ctrl 0x41260000 y3_audio_state 0x41270000 y3_audio_counts 0x41280000} {
    n4_connect $dsp_clk $inst/s_axi_aclk
    n4_connect $dsp_resetn $inst/s_axi_aresetn
    sentinel_axi $base $inst $dsp_clk $dsp_resetn S_AXI
}
n4_connect y3_audio_ctrl/gpio_io_o x5_frontend_0/audio_control
n4_connect y3_audio_ctrl/gpio2_io_o x5_frontend_0/audio_fcw
n4_connect x5_frontend_0/audio_status y3_audio_state/gpio_io_i
n4_connect x5_frontend_0/audio_frames y3_audio_state/gpio2_io_i
n4_connect x5_frontend_0/audio_underflows y3_audio_counts/gpio_io_i
n4_connect x5_frontend_0/audio_samples y3_audio_counts/gpio2_io_i
puts "Y3_AUDIO_WIRED: 8192 mono words, prefill4096, OUT1 codec bus0x41630000"
