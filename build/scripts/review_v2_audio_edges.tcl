# Read-only physical bounds for serializer transitions that occur only on BCLK fall.
set root [file normalize $::env(REPO)]
set reports [file join $root build reports sentinel_v2_100m audio_edges_r1]
if {[file exists $reports]} {error "Preserve prior edge review"}
file mkdir $reports
set_param general.maxThreads 8
open_project [file join $root build work adi_hdl projects fmcomms2 sentinel_v2_100m sentinel_v2_100m.xpr]
open_run impl_1
foreach {signal regex} {
    bclk {.*audio/serializer/phase_reg\[1\]/C}
    lrc {.*audio/serializer/lrck_reg/C}
    dacdat {.*audio/serializer/dacdat_reg/C}
} {
    set start [get_pins -hier -regexp $regex]
    if {[llength $start] != 1} {error "Unexpected serializer endpoint: $signal"}
    report_timing -from $start -to [get_ports aud_$signal] -delay_type min_max -max_paths 20 -nworst 10 -path_type full_clock_expanded -file [file join $reports ${signal}.rpt]
}
puts "V2_AUDIO_EDGE_REPORTS_READY_NOT_ACCEPTED"
