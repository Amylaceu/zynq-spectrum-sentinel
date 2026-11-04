# Independent OOC experiment, not another sentinel_v1c implementation round.
if {![info exists ::env(REPO)] || [llength $argv]!=1} {error "Need REPO and attempt"}
set root [file normalize $::env(REPO)]
set attempt [lindex $argv 0]
set out [file join $root build reports x2_timing_candidates_r$attempt]
if {[file exists $out]} {error "Preserve previous OOC evidence"}
file mkdir $out
set_param general.maxThreads 2
foreach {top source period clock} {
    drop_counter_reference sim/tb/drop_counter_reference.v 4.069 clk
    drop_counter_segmented src/rtl/x2_opt/drop_counter_segmented.v 4.069 clk
    cfar_cluster_x1 src/rtl/cfar_x1/cfar_cluster_x1.v 6.667 aclk
    cfar_cluster_timing_x2 src/rtl/x2_opt/cfar_cluster_timing_x2.v 6.667 aclk
} {
    create_project -in_memory -part xc7z020clg484-2
    read_verilog [file join $root $source]
    synth_design -top $top -part xc7z020clg484-2 -mode out_of_context
    create_clock -name test_clk -period $period [get_ports $clock]
    set data_inputs [get_ports -filter "DIRECTION == IN && NAME != $clock"]
    set_input_delay -clock test_clk 0 $data_inputs
    set_output_delay -clock test_clk 0 [all_outputs]
    opt_design
    place_design
    phys_opt_design
    route_design
    report_timing_summary -delay_type min_max -file [file join $out ${top}_timing.rpt]
    report_timing -delay_type max -max_paths 5 -file [file join $out ${top}_paths.rpt]
    report_utilization -file [file join $out ${top}_utilization.rpt]
    puts "X2_CANDIDATE_RESULT $top WNS=[get_property SLACK [get_timing_paths -delay_type max -max_paths 1]] WHS=[get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]"
    close_project
}
puts "X2_TIMING_CANDIDATES_AUDIT_COMPLETE"
