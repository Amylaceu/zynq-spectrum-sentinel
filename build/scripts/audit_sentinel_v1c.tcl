if {![info exists ::env(REPO)]} {error "Initialize tools/env.ps1"}
set root [file normalize $::env(REPO)]
set reports [file join $root build reports sentinel_v1c]
set project [file join $root build work adi_hdl projects fmcomms2 sentinel_v1c sentinel_v1c.xpr]
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
    error "Implementation did not complete write_bitstream: [get_property STATUS [get_runs impl_1]]"
}
if {[llength [get_cells -hier -filter {IS_BLACKBOX == 1}]]} {error "Unresolved blackboxes in final implementation"}
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $reports final_timing.rpt]
report_utilization -file [file join $reports final_utilization.rpt]
report_cdc -file [file join $reports final_cdc.rpt]
report_io -file [file join $reports final_io.rpt]
report_clocks -file [file join $reports final_clocks.rpt]
report_bus_skew -warn_on_violation -file [file join $reports final_bus_skew.rpt]
set wns [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set whs [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
puts "SENTINEL_FINAL_WNS $wns"
puts "SENTINEL_FINAL_WHS $whs"
if {$wns<0 || $whs<0} {error "Full-system routed timing fails"}

set drop_q [get_pins -hier -regexp {.*adc_tap_0/inst/drop_gray_reg\[[0-9]+\]/Q}]
set drop_d [get_pins -hier -regexp {.*adc_tap_0/inst/drop_sync0_reg\[[0-9]+\]/D}]
set drop_second [get_cells -hier -regexp {.*adc_tap_0/inst/drop_sync1_reg\[[0-9]+\]}]
if {[llength $drop_q]!=32 || [llength $drop_d]!=32 || [llength $drop_second]!=32} {error "Missing X2 counter CDC endpoints"}
foreach cell $drop_second {
    if {[get_property ASYNC_REG $cell] ne "TRUE"} {error "Counter CDC second stage lacks ASYNC_REG"}
}
report_bus_skew -from $drop_q -to $drop_d -warn_on_violation -file [file join $reports final_gray_bus_skew.rpt]
report_timing -from $drop_q -to $drop_d -max_paths 32 -file [file join $reports final_gray_paths.rpt]
puts "SENTINEL_FINAL_AUDIT_PASS"

