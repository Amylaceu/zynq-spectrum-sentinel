# Reuse the unchanged, successful synthesis; change implementation strategy only.
# Attempt 1 must be archived before this script is invoked.
set root [file normalize $::env(REPO)]
set archive [file join $root docs x2_implementation_r1_failure.json]
if {![file exists $archive]} {error "Archive failed implementation before reset"}
set_param general.maxThreads 2
set project [file join $root build work adi_hdl projects fmcomms2 sentinel_v1c sentinel_v1c.xpr]
open_project $project
if {[get_property STATUS [get_runs synth_1]] ne "synth_design Complete!"} {
    error "Unchanged completed synthesis required"
}
set choices [list_property_value strategy [get_runs impl_1]]
puts "X2_IMPLEMENTATION_STRATEGIES $choices"
if {[lsearch -exact $choices Performance_ExtraTimingOpt] < 0} {
    error "Expected implementation strategy unavailable"
}
reset_run impl_1
set_property strategy Performance_ExtraTimingOpt [get_runs impl_1]
launch_runs impl_1 -to_step write_bitstream -jobs 1
wait_on_run impl_1
if {[get_property STATUS [get_runs impl_1]] ne "write_bitstream Complete!"} {
    error "Implementation retry did not finish"
}
open_run impl_1
set reports [file join $root build reports sentinel_v1c]
file mkdir $reports
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $reports retry_r2_timing.rpt]
set setup [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set hold [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
puts "X2_RETRY_SETUP $setup HOLD $hold"
if {$setup < 0 || $hold < 0} {error "Implementation retry still fails timing"}
write_hw_platform -fixed -include_bit -force -file [file join $root build work adi_hdl projects fmcomms2 sentinel_v1c sentinel_v1c.sdk system_top.xsa]
