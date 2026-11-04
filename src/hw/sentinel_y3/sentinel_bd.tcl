# Prefer actual HDL pins over automatic one-signal interface aliases (e.g. adc_i).
proc n4_connect {a b} {
    if {$a in {GND VCC} || $b in {GND VCC}} {ad_connect $a $b;return}
    set pa [get_bd_pins -quiet $a]
    if {![llength $pa]} {set pa [get_bd_ports -quiet $a]}
    set pb [get_bd_pins -quiet $b]
    if {![llength $pb]} {set pb [get_bd_ports -quiet $b]}
    if {[llength $pa] && [llength $pb]} {connect_bd_net $pa $pb;return}
    set na [get_bd_nets -quiet $a]
    set nb [get_bd_nets -quiet $b]
    if {[llength $na] && [llength $pb]} {connect_bd_net -net $na $pb;return}
    if {[llength $nb] && [llength $pa]} {connect_bd_net -net $nb $pa;return}
    ad_connect $a $b
}
# Sentinel v1d: retain v1b spectrum/MMIO contract with timing-pipelined CFAR,
# and add PFB/capture plus LCD UI. X1 numeric equivalence is checked separately.
# The preserved PS PLL preset quantizes a requested FCLK2=150MHz to142.857MHz.
# Derive exact150MHz with MMCM from the already verified external50MHz LCD clock,
# keeping DDR/GEM/PS PLL settings unchanged. Both output clocks have real timing constraints.
create_bd_port -dir I -type clk lcd_clk
set_property CONFIG.FREQ_HZ 50000000 [get_bd_ports lcd_clk]
ad_ip_instance clk_wiz dsp_clock [list PRIM_IN_FREQ 50.000 CLKOUT1_REQUESTED_OUT_FREQ 150.000 \
    USE_RESET true RESET_TYPE ACTIVE_LOW USE_LOCKED true]
n4_connect lcd_clk dsp_clock/clk_in1
n4_connect sys_ps7/FCLK_RESET0_N dsp_clock/resetn
ad_ip_instance proc_sys_reset dsp_rstgen [list C_EXT_RST_WIDTH 1]
n4_connect dsp_clock/clk_out1 dsp_rstgen/slowest_sync_clk
n4_connect sys_ps7/FCLK_RESET0_N dsp_rstgen/ext_reset_in
n4_connect dsp_clock/locked dsp_rstgen/dcm_locked
set dsp_clk dsp_clock/clk_out1
set dsp_resetn dsp_rstgen/peripheral_aresetn
ad_ip_instance proc_sys_reset lcd_rstgen [list C_EXT_RST_WIDTH 1]
n4_connect lcd_clk lcd_rstgen/slowest_sync_clk
n4_connect sys_ps7/FCLK_RESET0_N lcd_rstgen/ext_reset_in
n4_connect VCC lcd_rstgen/dcm_locked
set lcd_resetn lcd_rstgen/peripheral_aresetn

foreach {module instance} {adc_tap adc_tap_0 sentinel_capture power_capture sentinel_events event_bridge} {
    create_bd_cell -type module -reference $module $instance
}
set_property CONFIG.ASSOCIATED_BUSIF m_axis [get_bd_pins adc_tap_0/dsp_clk]
set_property CONFIG.ASSOCIATED_BUSIF {} [get_bd_pins adc_tap_0/adc_clk]
create_bd_cell -type module -reference y3_frontend x5_frontend_0
n4_connect $dsp_clk x5_frontend_0/aclk
n4_connect $dsp_resetn x5_frontend_0/aresetn
ad_ip_instance src_mux src_mux_0
ad_ip_instance spec_front spec_front_0
ad_ip_instance cfar_core_x5 cfar_core_0
ad_ip_instance lcd8080_engine_x5 lcd_engine
ad_ip_instance perf_mon perf_mon_0
foreach inst {src_mux_0 spec_front_0 cfar_core_0 perf_mon_0} {
    n4_connect $dsp_clk $inst/aclk
    n4_connect $dsp_resetn $inst/aresetn
}
foreach inst {adc_tap_0 power_capture event_bridge lcd_engine} {
    n4_connect $dsp_clk $inst/dsp_clk
    n4_connect $dsp_resetn $inst/dsp_aresetn
}
n4_connect lcd_clk lcd_engine/aclk
n4_connect $lcd_resetn lcd_engine/aresetn
n4_connect lcd_clk event_bridge/lcd_clk
n4_connect $lcd_resetn event_bridge/lcd_aresetn
foreach inst {power_capture event_bridge} {
    n4_connect sys_cpu_clk $inst/cpu_clk
    n4_connect sys_cpu_resetn $inst/cpu_aresetn
}
n4_connect axi_ad9361/l_clk adc_tap_0/adc_clk
n4_connect axi_ad9361/rst adc_tap_0/adc_reset
foreach {from to} {adc_data_i0 adc_i adc_data_q0 adc_q adc_valid_i0 adc_valid_i adc_valid_q0 adc_valid_q} {
    n4_connect axi_ad9361/$from adc_tap_0/$to
}
n4_connect adc_tap_0/m_axis src_mux_0/s_axis_rf
# These observed streams use explicit pins throughout. Mixing interface nets and
# separate debug/performance pin taps makes IPI override and disconnect the other endpoints.
foreach signal {tdata tvalid tlast} {
    n4_connect src_mux_0/m_axis_$signal x5_frontend_0/s_axis_$signal
    n4_connect x5_frontend_0/m_axis_spec_$signal spec_front_0/s_axis_$signal
    n4_connect spec_front_0/m_axis_pwr_$signal cfar_core_0/s_axis_pwr_$signal
}
n4_connect x5_frontend_0/s_axis_tready src_mux_0/m_axis_tready
n4_connect spec_front_0/s_axis_tready x5_frontend_0/m_axis_spec_tready
n4_connect cfar_core_0/s_axis_pwr_tready spec_front_0/m_axis_pwr_tready
n4_connect spec_front_0/m_axis_db lcd_engine/s_axis_spec
n4_connect cfar_core_0/m_axis_thr lcd_engine/s_axis_thr
n4_connect VCC cfar_core_0/m_axis_hit_tready
n4_connect VCC cfar_core_0/m_axis_tgt_tready

# Explicit AXI clock converters: ADI CPU helper itself always uses CPU clock on its MI.
proc sentinel_axi {base inst clk resetn {bus s_axi}} {
    set bridge ${inst}_axi_cdc
    ad_ip_instance axi_clock_converter $bridge [list PROTOCOL AXI4LITE ADDR_WIDTH 32 DATA_WIDTH 32]
    n4_connect sys_cpu_clk $bridge/s_axi_aclk
    n4_connect sys_cpu_resetn $bridge/s_axi_aresetn
    n4_connect $clk $bridge/m_axi_aclk
    n4_connect $resetn $bridge/m_axi_aresetn
    n4_connect $bridge/M_AXI $inst/$bus
    # A clock converter is transparent and has no register segment of its own.
    # Connect the next GP0 MI manually, then map the actual downstream register block.
    set fabric [get_bd_cells axi_gp0_interconnect]
    set index [get_property CONFIG.NUM_MI $fabric]
    set mi [format "M%02d" $index]
    set_property CONFIG.NUM_MI [expr {$index+1}] $fabric
    if {[llength [get_bd_pins -quiet axi_gp0_interconnect/${mi}_ACLK]]} {
        n4_connect sys_cpu_clk axi_gp0_interconnect/${mi}_ACLK
        n4_connect sys_cpu_resetn axi_gp0_interconnect/${mi}_ARESETN
    }
    n4_connect axi_gp0_interconnect/${mi}_AXI $bridge/S_AXI
    set segments [get_bd_addr_segs -of_objects [get_bd_intf_pins $inst/$bus]]
    if {[llength $segments]!=1} {error "Expected one downstream register segment for $inst, got $segments"}
    set span [get_property RANGE $segments]
    if {$span<4096} {set span 4096}
    create_bd_addr_seg -range $span -offset $base [get_bd_addr_spaces sys_ps7/Data] $segments SEG_sentinel_$inst
}
sentinel_axi 0x43C00000 src_mux_0 $dsp_clk $dsp_resetn
sentinel_axi 0x43C10000 spec_front_0 $dsp_clk $dsp_resetn
sentinel_axi 0x43C20000 cfar_core_0 $dsp_clk $dsp_resetn
sentinel_axi 0x43C60000 lcd_engine lcd_clk $lcd_resetn
sentinel_axi 0x43C70000 perf_mon_0 $dsp_clk $dsp_resetn

# CPU-write/native-read 128KiB double UI bank. Native port is byte addressed.
proc sentinel_bram {control memory words base range} {
    ad_ip_instance axi_bram_ctrl $control [list DATA_WIDTH 32 SINGLE_PORT_BRAM 1]
    ad_ip_instance blk_mem_gen $memory [list Memory_Type True_Dual_Port_RAM \
        Use_Byte_Write_Enable true Byte_Size 8 Write_Width_A 32 Read_Width_A 32 Write_Depth_A $words \
        Write_Width_B 32 Read_Width_B 32 Enable_B Use_ENB_Pin \
        Register_PortA_Output_of_Memory_Primitives false Register_PortB_Output_of_Memory_Primitives false \
        Use_RSTA_Pin true Use_RSTB_Pin true]
    n4_connect $control/BRAM_PORTA $memory/BRAM_PORTA
    ad_cpu_interconnect $base $control
    set segment [get_bd_addr_segs -of_objects [get_bd_addr_spaces sys_ps7/Data] -filter "NAME =~ *${control}*"]
    if {[llength $segment]!=1} {error "Ambiguous BRAM segment $control"}
    set_property range $range $segment
}
sentinel_bram axi_lcd_ui lcd_ui_memory 32768 0x42100000 128K
n4_connect lcd_clk lcd_ui_memory/clkb
n4_connect lcd_rstgen/peripheral_reset lcd_ui_memory/rstb
n4_connect VCC lcd_ui_memory/enb
n4_connect GND lcd_ui_memory/web
n4_connect GND lcd_ui_memory/dinb
n4_connect lcd_engine/ui_addr lcd_ui_memory/addrb
n4_connect lcd_engine/ui_data lcd_ui_memory/doutb
foreach {name width} {lcd_data 16 lcd_cs_n 1 lcd_rs 1 lcd_wr_n 1 lcd_rd_n 1 lcd_reset_n 1} {
    if {$width==1} {create_bd_port -dir O $name} else {create_bd_port -dir O -from [expr {$width-1}] -to 0 $name}
    n4_connect $name lcd_engine/$name
}

# Independent replay MM2S and SCAP S2MM, simple mode, 23-bit transfer length.
ad_ip_instance axi_dma axi_dma_replay [list c_include_sg 0 c_include_s2mm 1 c_include_mm2s 1 \
    c_m_axi_s2mm_data_width 32 c_s_axis_s2mm_tdata_width 32 c_include_s2mm_dre 0 c_m_axi_mm2s_data_width 32 c_m_axis_mm2s_tdata_width 32 c_sg_length_width 23 c_include_mm2s_dre 0]
n4_connect sys_cpu_clk axi_dma_replay/s_axi_lite_aclk
n4_connect sys_cpu_clk axi_dma_replay/m_axi_mm2s_aclk
n4_connect sys_cpu_clk axi_dma_replay/m_axi_s2mm_aclk
n4_connect sys_cpu_resetn axi_dma_replay/axi_resetn
ad_cpu_interconnect 0x40400000 axi_dma_replay
ad_mem_hp0_interconnect sys_cpu_clk sys_ps7/S_AXI_HP0
ad_mem_hp0_interconnect sys_cpu_clk axi_dma_replay/M_AXI_MM2S
ad_mem_hp0_interconnect sys_cpu_clk axi_dma_replay/M_AXI_S2MM
ad_ip_instance axis_clock_converter replay_cdc [list TDATA_NUM_BYTES 4 HAS_TLAST 1 SYNCHRONIZATION_STAGES 3]
n4_connect sys_cpu_clk replay_cdc/s_axis_aclk
n4_connect sys_cpu_resetn replay_cdc/s_axis_aresetn
n4_connect $dsp_clk replay_cdc/m_axis_aclk
n4_connect $dsp_resetn replay_cdc/m_axis_aresetn
n4_connect axi_dma_replay/M_AXIS_MM2S replay_cdc/S_AXIS
n4_connect replay_cdc/M_AXIS src_mux_0/s_axis_replay
ad_cpu_interrupt ps-9 mb-9 axi_dma_replay/mm2s_introut

# Non-intrusive full power-frame readback for bit-exact replay self-test; first complete frame after toggle.
sentinel_bram axi_power_capture power_capture_memory 2048 0x42010000 8K
n4_connect $dsp_clk power_capture_memory/clkb
n4_connect power_capture/mem_reset power_capture_memory/rstb
n4_connect power_capture/mem_en power_capture_memory/enb
n4_connect power_capture/mem_we power_capture_memory/web
n4_connect power_capture/mem_addr power_capture_memory/addrb
n4_connect power_capture/mem_data power_capture_memory/dinb
ad_ip_instance axi_gpio axi_capture_ctrl [list C_GPIO_WIDTH 1 C_ALL_OUTPUTS 1 C_DOUT_DEFAULT 0x00000000 \
    C_IS_DUAL 1 C_GPIO2_WIDTH 2 C_ALL_INPUTS_2 1]
ad_cpu_interconnect 0x41220000 axi_capture_ctrl
n4_connect axi_capture_ctrl/gpio_io_o power_capture/arm_toggle
ad_ip_instance xlconcat capture_status [list NUM_PORTS 2]
n4_connect power_capture/done_toggle capture_status/In0
n4_connect power_capture/error_sticky capture_status/In1
n4_connect capture_status/dout axi_capture_ctrl/gpio2_io_i
foreach {from to} {m_axis_pwr_tdata power_data m_axis_pwr_tuser power_bin m_axis_pwr_tvalid power_valid m_axis_pwr_tready power_ready m_axis_pwr_tlast power_last} {
    n4_connect spec_front_0/$from power_capture/$to
}

# All perf event taps are synchronous at 150MHz, and only count actual handshakes.
foreach {from to} {m_axis_tvalid sample_valid m_axis_tready sample_ready} {n4_connect src_mux_0/$from perf_mon_0/$to}
foreach {from to} {m_axis_pwr_tvalid fft_valid m_axis_pwr_tready fft_ready m_axis_pwr_tlast fft_last} {n4_connect spec_front_0/$from perf_mon_0/$to}
foreach {from to} {m_axis_hit_tvalid hit_valid m_axis_hit_tready hit_ready irq_list_ready list_ready} {n4_connect cfar_core_0/$from perf_mon_0/$to}
ad_ip_instance xlslice hit_bit [list DIN_WIDTH 8 DIN_FROM 0 DIN_TO 0 DOUT_WIDTH 1]
n4_connect cfar_core_0/m_axis_hit_tdata hit_bit/Din
n4_connect hit_bit/Dout perf_mon_0/hit_value
n4_connect adc_tap_0/overflow_sticky perf_mon_0/overflow_sticky
n4_connect adc_tap_0/fifo_level perf_mon_0/fifo_level
n4_connect src_mux_0/error_sticky event_bridge/src_error
n4_connect spec_front_0/error_sticky event_bridge/spec_error
n4_connect adc_tap_0/mismatch_sticky event_bridge/adc_error
n4_connect event_bridge/dsp_error perf_mon_0/error_sticky

# Pulse-toggle bridges avoid losing 150MHz list-ready pulses at the CPU interrupt controller.
n4_connect cfar_core_0/irq_list_ready event_bridge/cfar_irq
n4_connect lcd_engine/irq_frame_done event_bridge/lcd_irq
ad_ip_instance axi_intc axi_sentinel_intc [list C_KIND_OF_INTR 0x00000001 C_HAS_FAST 0 C_IRQ_CONNECTION 1]
n4_connect sys_cpu_clk axi_sentinel_intc/s_axi_aclk
n4_connect sys_cpu_resetn axi_sentinel_intc/s_axi_aresetn
n4_connect event_bridge/interrupt_any axi_sentinel_intc/intr
ad_cpu_interconnect 0x41800000 axi_sentinel_intc
ad_cpu_interrupt ps-8 mb-8 axi_sentinel_intc/irq

# X5 DSP-clocked GPIOs: config handshake has no unsynchronized CPU bus crossing.
ad_ip_instance axi_gpio x5_ctrl [list C_GPIO_WIDTH 32 C_ALL_OUTPUTS 1 C_DOUT_DEFAULT 0x00000000 C_IS_DUAL 1 C_GPIO2_WIDTH 32 C_ALL_OUTPUTS_2 1]
ad_ip_instance axi_gpio x5_meta [list C_GPIO_WIDTH 32 C_ALL_OUTPUTS 1 C_DOUT_DEFAULT 0x00000000]
ad_ip_instance axi_gpio x5_status [list C_GPIO_WIDTH 32 C_ALL_INPUTS 1]
foreach inst {x5_ctrl x5_meta x5_status} {
    n4_connect $dsp_clk $inst/s_axi_aclk
    n4_connect $dsp_resetn $inst/s_axi_aresetn
}
sentinel_axi 0x41230000 x5_ctrl $dsp_clk $dsp_resetn S_AXI
sentinel_axi 0x41240000 x5_meta $dsp_clk $dsp_resetn S_AXI
sentinel_axi 0x41250000 x5_status $dsp_clk $dsp_resetn S_AXI
n4_connect x5_ctrl/gpio_io_o x5_frontend_0/control
n4_connect x5_ctrl/gpio2_io_o x5_frontend_0/fcw
n4_connect x5_meta/gpio_io_o x5_frontend_0/source_id
n4_connect x5_status/gpio_io_i x5_frontend_0/status
ad_ip_instance axis_clock_converter capture_cdc [list TDATA_NUM_BYTES 4 HAS_TLAST 1 HAS_TKEEP 1 SYNCHRONIZATION_STAGES 3]
n4_connect $dsp_clk capture_cdc/s_axis_aclk
n4_connect $dsp_resetn capture_cdc/s_axis_aresetn
n4_connect sys_cpu_clk capture_cdc/m_axis_aclk
n4_connect sys_cpu_resetn capture_cdc/m_axis_aresetn
foreach signal {tdata tkeep tvalid tlast tready} {
    n4_connect x5_frontend_0/m_axis_capture_$signal capture_cdc/s_axis_$signal
}
n4_connect capture_cdc/M_AXIS axi_dma_replay/S_AXIS_S2MM
ad_cpu_interrupt ps-10 mb-10 axi_dma_replay/s2mm_introut

source [file join [file dirname [info script]] audio_y3_bd.tcl]

# Persist concrete connections and addresses for acceptance, not just Tcl syntax checks.
validate_bd_design
# A successful validate command alone may still have auto-grounded unconnected AXIS inputs.
foreach pin {src_mux_0/m_axis_tready spec_front_0/s_axis_tvalid spec_front_0/s_axis_tdata
    spec_front_0/m_axis_pwr_tready cfar_core_0/s_axis_pwr_tvalid cfar_core_0/s_axis_pwr_tdata
    perf_mon_0/sample_ready perf_mon_0/fft_ready power_capture/power_ready
    x5_frontend_0/s_axis_tvalid x5_frontend_0/m_axis_spec_tready
    x5_frontend_0/m_axis_capture_tready x5_frontend_0/control x5_frontend_0/fcw
    x5_frontend_0/source_id x5_ctrl/s_axi_aclk x5_meta/s_axi_aclk x5_status/s_axi_aclk} {
    set net [get_bd_nets -of_objects [get_bd_pins $pin]]
    set drivers [get_bd_pins -of_objects $net -filter {DIR == O}]
    if {[llength $drivers]!=1} {error "Unconnected or multiply driven critical path $pin: $drivers"}
    if {[string match *GND* $drivers]} {error "Critical path grounded: $pin"}
    puts "SENTINEL_DRIVER $pin $drivers"
}
if {[get_property CONFIG.C_NUM_INTR_INPUTS [get_bd_cells axi_sentinel_intc]]!=1} {error "Unexpected aggregate IRQ width"}
save_bd_design
set address_file [open [file normalize $::env(REPO)/logs/Y3_bd_addresses.txt] w]
foreach seg [get_bd_addr_segs -of_objects [get_bd_addr_spaces sys_ps7/Data]] {
    puts $address_file "$seg [get_property OFFSET $seg] [get_property RANGE $seg]"
}
close $address_file
puts "SENTINEL_CONNECTIONS_CREATED"
