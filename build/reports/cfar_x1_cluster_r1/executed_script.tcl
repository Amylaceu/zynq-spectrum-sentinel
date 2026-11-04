if {![info exists ::env(REPO)]} {error "Initialize tools/env.ps1"}
if {[llength $argv] != 1} {error "Usage: attempt (1..3)"}
set attempt [lindex $argv 0]
if {![string is integer -strict $attempt] || $attempt<1 || $attempt>3} {error "Invalid attempt"}
set root [file normalize $::env(REPO)]
set out [file join $root build reports cfar_x1_cluster_r$attempt]
if {[file exists $out]} {error "Preserve previous reports"}
file mkdir $out
set_param general.maxThreads 2
create_project -in_memory -part xc7z020clg484-2
read_verilog [file join $root src rtl cfar_x1 cfar_cluster_x1.v]
set xdc [file join $out clock.xdc]
set fd [open $xdc w]
puts $fd {create_clock -name module_clk -period 6.666667 [get_ports aclk]}
puts $fd {set_input_delay -clock module_clk 0 [get_ports -filter {DIRECTION == IN && NAME != aclk}]}
puts $fd {set_output_delay -clock module_clk 0 [get_ports -filter {DIRECTION == OUT}]}
close $fd
read_xdc $xdc
synth_design -top cfar_cluster_x1 -part xc7z020clg484-2 -mode out_of_context
opt_design
place_design
route_design
if {[llength [get_cells -hierarchical -filter {IS_BLACKBOX == 1}]]} {error "Blackboxes remain"}
report_utilization -file [file join $out utilization.rpt]
report_timing_summary -file [file join $out timing.rpt]
report_timing -max_paths 5 -file [file join $out critical_paths.rpt]
set registers [all_registers]
report_timing -delay_type min -from $registers -to $registers -max_paths 3 -file [file join $out internal_hold.rpt]
set setup_path [get_timing_paths -delay_type max -max_paths 1]
set hold_path [get_timing_paths -delay_type min -from $registers -to $registers -max_paths 1]
if {![llength $setup_path] || ![llength $hold_path]} {error "Missing constrained paths"}
set wns [get_property SLACK $setup_path]
set hold [get_property SLACK $hold_path]
set fd [open [file join $out result.json] w]
puts $fd [format {{"wns_ns": %s, "internal_hold_ns": %s}} $wns $hold]
close $fd
puts "X1_CLUSTER_OOC_WNS $wns"
puts "X1_CLUSTER_INTERNAL_HOLD $hold"
if {$wns<0 || $hold<0} {error "X1 cluster OOC timing failed"}
puts "X1_CLUSTER_OOC_PASS (standalone cluster only, not full-system acceptance)"
