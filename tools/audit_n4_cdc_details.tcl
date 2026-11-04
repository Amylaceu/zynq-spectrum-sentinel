# Read-only follow-up to the final timing/resource audit; never rebuilds.
if {![info exists ::env(REPO)]} {error "Initialize tools/env.ps1"}
set root [file normalize $::env(REPO)]
set out [file join $root build reports sentinel_v1]
set_param general.maxThreads 2
open_project [file join $root build work adi_hdl projects fmcomms2 sentinel_v1 sentinel_v1.xpr]
open_run impl_1
report_cdc -details -file [file join $out final_cdc_details.rpt]
report_bus_skew -file [file join $out final_bus_skew.rpt]
report_exceptions -coverage -file [file join $out final_exceptions_coverage.rpt]
report_methodology -file [file join $out final_methodology.rpt]
puts "N4_CDC_DETAILS_COMPLETE"
