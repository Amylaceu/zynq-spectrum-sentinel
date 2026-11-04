# Link attempt 2: only reuse existing checkpoints, no synthesis commands.
# Run in an empty non-project context to avoid opening the source project twice.
set root [file normalize $::env(REPO)]
set project [file join $root build/work/adi_hdl/projects/fmcomms2/sentinel_z2]
set output [file join $root build/work/z2_link_attempt2]
if {[file exists $output]} {error "Preserve previous link attempt"}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint [file join $root build/work/z2_diagnostic_1/system_top.dcp]
puts "Z2_TOP_CHECKPOINT_OPEN"
flush stdout
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
        puts "Z2_LINK $box [dict get $index $reference]"
        flush stdout
        read_checkpoint -cell $box [dict get $index $reference]
    }
}
if {[llength [get_cells -hier -filter {IS_BLACKBOX == 1}]]} {error "Unresolved Z2 blackboxes"}
report_utilization -file [file join $output linked_utilization.rpt]
report_drc -file [file join $output linked_drc.rpt]
report_clocks -file [file join $output linked_clocks.rpt]
write_checkpoint [file join $output linked.dcp]
puts "Z2_NONPROJECT_LINK_PASS"
exit 0
