# Read-only comparison of retained third-round checkpoints. No run is reset.
if {![info exists ::env(REPO)]} {error "Initialize tools/env.ps1 first"}
set root [file normalize $::env(REPO)]
set run [file join $root build work adi_hdl projects fmcomms2 sentinel_v2_100m sentinel_v2_100m.runs impl_1]
set output [file join $root build reports sentinel_v2_100m power_inspection_r1]
if {[file exists $output]} {error "Preserve prior inspection: $output"}
file mkdir $output
set_param general.maxThreads 8
foreach {stage filename} {
    opt system_top_opt.dcp
    power system_top_pwropt.dcp
    final system_top_postroute_physopt.dcp
} {
    set checkpoint [file join $run $filename]
    if {![file exists $checkpoint]} {error "Missing retained checkpoint: $checkpoint"}
    open_checkpoint $checkpoint
    set target {.*i_tx/i_up_dac_common/i_clock_mon/.*}
    set counter [get_cells -quiet -hier -regexp $target]
    if {![llength $counter]} {error "Clock monitor hierarchy not found"}
    set gates [get_cells -quiet -hier -regexp {.*i_tx/i_up_dac_common/i_clock_mon/.*cooolgate.*}]
    set fd [open [file join $output ${stage}_cells.txt] w]
    puts $fd "checkpoint $filename"
    puts $fd "clock_monitor_cells [llength $counter]"
    puts $fd "clock_monitor_cooolgate_cells [llength $gates]"
    foreach cell [lsort $counter] {
        puts $fd "cell $cell [get_property REF_NAME $cell]"
    }
    set registers [get_cells -quiet -hier -regexp {.*i_tx/i_up_dac_common/i_clock_mon/d_count_reg\[[0-9]+\]}]
    puts $fd "counter_register_count [llength $registers]"
    foreach cell [lsort $registers] {
        set ce [get_pins -quiet $cell/CE]
        if {![llength $ce]} {continue}
        set net [get_nets -quiet -of_objects $ce]
        puts $fd "ce_net $ce $net"
        foreach driver [get_pins -quiet -of_objects $net -filter {DIRECTION == OUT}] {
            puts $fd "ce_driver $driver"
        }
    }
    close $fd
    set sources [get_pins -quiet -hier -regexp {.*i_tx/i_up_dac_common/i_clock_mon/d_count_reg\[32\]/Q}]
    set sinks [get_pins -quiet -hier -regexp {.*i_tx/i_up_dac_common/i_clock_mon/d_count_reg\[[0-9]+\]/CE}]
    if {![llength $sources] || ![llength $sinks]} {error "Counter endpoints changed"}
    report_timing -from $sources -to $sinks -delay_type max -max_paths 5 -file [file join $output ${stage}_counter_setup.rpt]
    puts "Z10_POWER_INSPECTION_STAGE $stage cells=[llength $counter] gates=[llength $gates]"
    close_design
}
puts "Z10_POWER_INSPECTION_COMPLETE $output"
