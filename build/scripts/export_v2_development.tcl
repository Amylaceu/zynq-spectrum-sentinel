# Inspect and export the existing route; no implementation/constraint changes.
set root [file normalize $::env(REPO)]
set reports [file join $root build reports sentinel_v2_100m development_export_r1]
if {[file exists $reports]} {error "Preserve prior export"}
file mkdir $reports
open_project [file join $root build work adi_hdl projects fmcomms2 sentinel_v2_100m sentinel_v2_100m.xpr]
open_run impl_1
check_timing -verbose -file [file join $reports check_timing_verbose.rpt]
report_timing -to [get_ports {lcd_data[*] lcd_rs lcd_wr_n lcd_reset_n}] -delay_type min_max -max_paths 200 -nworst 2 -file [file join $reports lcd_min_max.rpt]
report_exceptions -write_valid_exceptions -file [file join $reports valid_exceptions.xdc]
set fd [open [file join $reports export_status.txt] w]
puts $fd "impl_status [get_property STATUS [get_runs impl_1]]"
puts $fd "impl_directory [get_property DIRECTORY [get_runs impl_1]]"
puts $fd "wns [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]"
puts $fd "whs [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]"
close $fd
write_hw_platform -fixed -include_bit -file [file join $reports sentinel_v2_100m.xsa]
puts "V2_CANDIDATE_EXPORTED_NOT_ACCEPTED"
