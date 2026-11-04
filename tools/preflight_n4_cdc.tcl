# Validate the N4 CDC exceptions against the last routed checkpoint.
# Usage: vivado -mode batch -source tools/preflight_n4_cdc.tcl -tclargs DCP XDC REPORT
if {$argc != 3} {error "Expected routed checkpoint, CDC XDC, and report path"}
set dcp [file normalize [lindex $argv 0]]
set xdc [file normalize [lindex $argv 1]]
set report [file normalize [lindex $argv 2]]
open_checkpoint $dcp
set status_sync_first [get_pins -hier -regexp {.*adc_tap_0/inst/(overflow_sync_reg\[0\]|mismatch_sync_reg\[0\])/D}]
set reset_async_preset [get_pins -hier -regexp {.*adc_tap_0/inst/reset_sync_reg\[[0-2]\]/PRE}]
puts "N4_CDC_MATCH status_first_D=[llength $status_sync_first] reset_PRE=[llength $reset_async_preset]"
if {[llength $status_sync_first] != 2 || [llength $reset_async_preset] != 3} {error "N4 CDC pins differ from expected netlist"}
read_xdc $xdc
report_timing_summary -delay_type min_max -report_unconstrained -file $report
puts "N4_CDC_PREFLIGHT_PASS report=$report"
