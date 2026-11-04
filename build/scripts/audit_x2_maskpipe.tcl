# Core-level timing experiment only; never packages or loads a bitstream.
if {![info exists ::env(REPO)] || [llength $argv]!=1} {error "Need REPO and attempt"}
set root [file normalize $::env(REPO)]
set out [file join $root build reports x2_maskpipe_r[lindex $argv 0]]
if {[file exists $out]} {error "Preserve previous audit"}
file mkdir $out
set_param general.maxThreads 2
set tops {cfar_reference_regwrap cfar_maskpipe_regwrap}
if {[lindex $argv 0]==3} {set tops {cfar_cfgpipe_regwrap}}
foreach top $tops {
    create_project -in_memory -part xc7z020clg484-2
    foreach source [glob [file join $root src rtl cfar_x1 *.v]] {read_verilog $source}
    read_verilog [file join $root src rtl cfar cfar_occupancy.v]
    read_verilog [file join $root src rtl common axis_broadcast2.v]
    read_verilog [file join $root src rtl x2_opt cfar_core_maskpipe_x2.v]
    if {[lindex $argv 0]==3} {read_verilog [file join $root src rtl x2_opt cfar_core_cfgpipe_x2.v]}
    read_verilog [file join $root sim tb ${top}.v]
    add_files -norecurse [file join $root data reference spectrum spec_log_mantissa.hex]
    synth_design -top $top -part xc7z020clg484-2 -mode out_of_context
    create_clock -name test_clk -period 6.667 [get_ports aclk]
    set_input_delay -clock test_clk 0 [get_ports -filter {DIRECTION == IN && NAME != aclk}]
    set_output_delay -clock test_clk 0 [all_outputs]
    opt_design
    place_design
    phys_opt_design
    route_design
    report_timing_summary -delay_type min_max -file [file join $out ${top}_timing.rpt]
    set regs [all_registers -clock test_clk]
    report_timing -from $regs -to $regs -delay_type max -max_paths 10 -file [file join $out ${top}_reg_setup.rpt]
    report_timing -from $regs -to $regs -delay_type min -max_paths 10 -file [file join $out ${top}_reg_hold.rpt]
    report_utilization -file [file join $out ${top}_utilization.rpt]
    puts "X2_MASKPIPE_RESULT $top REG_WNS=[get_property SLACK [get_timing_paths -from $regs -to $regs -delay_type max -max_paths 1]] REG_WHS=[get_property SLACK [get_timing_paths -from $regs -to $regs -delay_type min -max_paths 1]]"
    close_project
}
puts "X2_MASKPIPE_AUDIT_COMPLETE"
