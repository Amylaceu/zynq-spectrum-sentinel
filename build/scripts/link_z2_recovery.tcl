# Recover the already synthesized Z2 netlist. Never call synth_design/launch_runs.
# Prior OOC outputs and top checkpoint are hashed before and after by the host.
set root [file normalize $::env(REPO)]
set project [file join $root build/work/adi_hdl/projects/fmcomms2/sentinel_z2]
set output [file join $root build/work/z2_route_recovery_r2]
file mkdir $output
set_param general.maxThreads 2
open_project [file join $project sentinel_z2.xpr]
open_checkpoint [file join $root build/work/z2_diagnostic_1/system_top.dcp]
set candidates [glob -nocomplain [file join $project sentinel_z2.runs *_synth_1 *.dcp]]
lappend candidates [file join $root build/work/x5_fft/x5_fft.gen/sources_1/ip/pfb_fft16/pfb_fft16.dcp]
set index [dict create]
foreach path $candidates {
    set name [file rootname [file tail $path]]
    if {[dict exists $index $name]} {error "Ambiguous checkpoint: $name"}
    dict set index $name $path
}
for {set level 0} {$level<5} {incr level} {
    set boxes [get_cells -hier -filter {IS_BLACKBOX == 1}]
    if {![llength $boxes]} {break}
    foreach box $boxes {
        set reference [get_property REF_NAME $box]
        if {![dict exists $index $reference]} {error "Missing checkpoint for $box / $reference"}
        set path [dict get $index $reference]
        puts "Z2_LINK $box $path"
        read_checkpoint -cell $box $path
    }
}
if {[llength [get_cells -hier -filter {IS_BLACKBOX == 1}]]} {error "Unresolved Z2 blackboxes"}
report_utilization -file [file join $output linked_utilization.rpt]
report_drc -file [file join $output linked_drc.rpt]
write_checkpoint [file join $output linked.dcp]
puts "Z2_RECOVERY_LINK_PASS"
exit 0
