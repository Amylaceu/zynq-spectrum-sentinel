if {![info exists ::env(REPO)]} {error "Initialize tools/env.ps1"}
set root [file normalize $::env(REPO)]
set reports [file join $root build reports sentinel_y3]
set project [file join $root build work adi_hdl projects fmcomms2 sentinel_y3 sentinel_y3.xpr]
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
foreach port {aud_mclk aud_bclk aud_lrc aud_dacdat audio_iic_scl audio_iic_sda} {if {[llength [get_ports $port]] != 1} {error "Missing Y3 audio port $port"}}
foreach cell {audio_bclk_buf audio_lrc_buf} {if {[llength [get_cells -hier -filter "NAME =~ *$cell"]] != 1} {error "Missing codec-safe OBUFT $cell"}}
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
puts "SENTINEL_FINAL_AUDIT_PASS"

