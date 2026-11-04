if {![info exists ::env(REPO)]} {error "Initialize tools/env.ps1"}
set root [file normalize $::env(REPO)]
set reports [file join $root build reports modules]
set_param general.maxThreads 2
create_project -in_memory -part xc7z020clg484-2
read_verilog [glob [file join $root src rtl lcd *.v]]
read_verilog [list [file join $root src rtl regs lcd_ctrl_regs.v] [file join $root src rtl spectrum spec_display_reduce.v]]
set_property include_dirs [list [file join $root src rtl common]] [current_fileset]
set xdc [file join $root build work module_constraints lcd8080_engine.xdc]
file mkdir [file dirname $xdc]
set f [open $xdc w]
puts $f {create_clock -name lcd_clk -period 20 [get_ports aclk]}
puts $f {create_clock -name dsp_clk -period 6.667 [get_ports dsp_clk]}
puts $f {set_clock_groups -asynchronous -group lcd_clk -group dsp_clk}
puts $f {set_input_delay -clock lcd_clk 0 [get_ports -filter {DIRECTION == IN && (NAME =~ s_axi_* || NAME =~ ui_data* || NAME == aresetn)}]}
puts $f {set_output_delay -clock lcd_clk 0 [get_ports -filter {DIRECTION == OUT && (NAME =~ s_axi_* || NAME =~ ui_addr* || NAME =~ lcd_* || NAME == irq_frame_done)}]}
puts $f {set_input_delay -clock dsp_clk 0 [get_ports -filter {DIRECTION == IN && (NAME =~ s_axis_* || NAME == dsp_aresetn)}]}
puts $f {set_output_delay -clock dsp_clk 0 [get_ports -filter {DIRECTION == OUT && NAME =~ s_axis_*}]}
close $f
read_xdc $xdc
synth_design -top lcd8080_engine -part xc7z020clg484-2 -mode out_of_context
opt_design
place_design
route_design
if {[llength [get_cells -hier -filter {IS_BLACKBOX == 1}]]} {error "Unresolved blackboxes"}
set bram [get_cells -hier -filter {REF_NAME =~ RAMB* && NAME =~ *snapshots*}]
puts "LCD_SNAPSHOT_BRAMS [llength $bram]"
if {[llength $bram]<2} {error "Snapshot memory must infer BRAM"}
report_utilization -file [file join $reports lcd8080_engine_util.rpt]
report_timing_summary -file [file join $reports lcd8080_engine_timing.rpt]
report_cdc -file [file join $reports lcd8080_engine_cdc.rpt]
set regs [all_registers]
report_timing -delay_type min -from $regs -to $regs -max_paths 4 -file [file join $reports lcd8080_engine_internal_hold.rpt]
set setup [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set hold [get_property SLACK [get_timing_paths -delay_type min -from $regs -to $regs -max_paths 1]]
puts "LCD_ENGINE_SETUP_WNS $setup"
puts "LCD_ENGINE_INTERNAL_HOLD $hold"
write_checkpoint -force [file join $reports lcd8080_engine_routed.dcp]
if {$setup<0 || $hold<0} {error "LCD engine timing fails"}
puts "LCD_ENGINE_IMPLEMENTATION_PASS"
