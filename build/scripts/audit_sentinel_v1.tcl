if {![info exists ::env(REPO)]} {error "Initialize tools/env.ps1"}
set root [file normalize $::env(REPO)]
set reports [file join $root build reports sentinel_v1]
set project [file join $root build work adi_hdl projects fmcomms2 sentinel_v1 sentinel_v1.xpr]
set_param general.maxThreads 2
open_project $project
open_run impl_1
set status_sync_first [get_pins -hier -regexp {.*adc_tap_0/inst/(overflow_sync_reg\[0\]|mismatch_sync_reg\[0\])/D}]
set reset_async_preset [get_pins -hier -regexp {.*adc_tap_0/inst/reset_sync_reg\[[0-2]\]/PRE}]
if {[llength $status_sync_first] != 2 || [llength $reset_async_preset] != 3} {
    error "ADC CDC synchronizer netlist changed; inspect exceptions before board use"
}
puts "SENTINEL_CDC_MATCH first_D=[llength $status_sync_first] async_PRE=[llength $reset_async_preset]"
if {[get_property STATUS [get_runs impl_1]] ne "write_bitstream Complete!"} {
    puts "IMPLEMENTATION_STATUS [get_property STATUS [get_runs impl_1]]"
}
if {[llength [get_cells -hier -filter {IS_BLACKBOX == 1}]]} {error "Unresolved blackboxes in final implementation"}
report_timing_summary -delay_type min_max -file [file join $reports final_timing.rpt]
report_utilization -file [file join $reports final_utilization.rpt]
report_cdc -file [file join $reports final_cdc.rpt]
report_clocks -file [file join $reports final_clocks.rpt]
set wns [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set whs [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
puts "SENTINEL_FINAL_WNS $wns"
puts "SENTINEL_FINAL_WHS $whs"
if {$wns<0 || $whs<0} {error "Full-system routed timing fails"}
puts "SENTINEL_FINAL_AUDIT_PASS"
