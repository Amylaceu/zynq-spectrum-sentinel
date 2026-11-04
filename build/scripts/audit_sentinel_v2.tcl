# Read-only post-route audit for the independent 100 MHz candidate.
# Run only after the implementation process has exited; never on a live build.
if {![info exists ::env(REPO)]} {error "Initialize tools/env.ps1 first"}
set root [file normalize $::env(REPO)]
set project [file join $root build work adi_hdl projects fmcomms2 sentinel_v2_100m sentinel_v2_100m.xpr]
if {![file exists $project]} {error "Missing v2 project: $project"}
if {![info exists ::env(SENTINEL_AUDIT_TAG)] ||
    ![regexp {^[a-zA-Z0-9_]+$} $::env(SENTINEL_AUDIT_TAG)]} {
    error "Set SENTINEL_AUDIT_TAG to a unique alphanumeric/underscore tag"
}
set reports [file join $root build reports sentinel_v2_100m audit_$::env(SENTINEL_AUDIT_TAG)]
if {[file exists $reports]} {error "Preserve previous audit: $reports"}
file mkdir $reports
set_param general.maxThreads 8
open_project $project
puts "Z10_AUDIT_IMPL_STATUS [get_property STATUS [get_runs impl_1]]"
open_run impl_1
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $reports timing.rpt]
report_exceptions -summary -file [file join $reports exceptions_summary.rpt]
report_exceptions -ignored -file [file join $reports exceptions_ignored.rpt]
report_exceptions -coverage -file [file join $reports exceptions_coverage.rpt]
report_clock_interaction -file [file join $reports clock_interaction.rpt]
report_cdc -details -file [file join $reports cdc.rpt]
report_bus_skew -file [file join $reports bus_skew.rpt]
report_route_status -file [file join $reports route_status.rpt]
report_drc -file [file join $reports drc.rpt]
report_methodology -file [file join $reports methodology.rpt]
report_io -file [file join $reports io.rpt]
report_clocks -file [file join $reports clocks.rpt]
report_utilization -file [file join $reports utilization.rpt]
report_utilization -hierarchical -hierarchical_depth 4 -file [file join $reports utilization_hierarchy.rpt]
report_timing -delay_type max -max_paths 40 -nworst 3 -sort_by group -file [file join $reports critical_setup.rpt]
report_timing -delay_type min -max_paths 20 -nworst 2 -sort_by group -file [file join $reports critical_hold.rpt]
set status_sync_first [get_pins -hier -regexp {.*adc_tap_0/inst/(overflow_sync_reg\[0\]|mismatch_sync_reg\[0\])/D}]
set audio_sync_first [get_pins -hier -regexp {.*audio_drive_meta_reg/D}]
set fd [open [file join $reports endpoint_audit.txt] w]
puts $fd "adc_status_first_stage_count [llength $status_sync_first]"
foreach pin $status_sync_first {puts $fd "adc_status_first_stage $pin"}
puts $fd "audio_first_stage_count [llength $audio_sync_first]"
foreach pin $audio_sync_first {puts $fd "audio_first_stage $pin"}
puts $fd "global_wns_ns [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]"
puts $fd "global_whs_ns [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]"
set unsafe_fifo_reset [get_pins -quiet -hier -regexp {.*adc_tap_0/inst/fifo_reset_reg/D}]
puts $fd "unsafe_fifo_reset_d_count [llength $unsafe_fifo_reset]"
puts $fd "blackbox_count [llength [get_cells -quiet -hier -filter {IS_BLACKBOX == 1}]]"
close $fd
if {[llength $status_sync_first] != 2 || [llength $audio_sync_first] != 1} {
    error "CDC exception endpoint changed; inspect endpoint_audit.txt before deployment"
}
if {[llength $unsafe_fifo_reset]} {error "Unsafe FIFO reset bypass remains in final netlist"}
puts "Z10_AUDIT_REPORTS_READY $reports"
