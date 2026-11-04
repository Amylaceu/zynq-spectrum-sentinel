# Read-only in-memory timing view of r2. The checkpoint is never rewritten.
# Reset the serializer-specific max-delay exception ONLY in this process so
# report_timing can expose the minimum physical C-to-pad delay and clock tree.
set root [file normalize $::env(REPO)]
set reports [file join $root build reports sentinel_v2_100m audio_early_r2b]
if {[file exists $reports]} {error "Preserve prior audio-early audit"}
file mkdir $reports
set_param general.maxThreads 8
open_checkpoint [file join $root build reports sentinel_v2_100m audio_route_repair_r2 repaired.dcp]
foreach {signal regex} {
    bclk {.*audio/serializer/phase_reg\[1\]/C}
    lrc {.*audio/serializer/lrck_reg/C}
    dacdat {.*audio/serializer/dacdat_reg/C}
} {
    set start [get_pins -hier -regexp $regex]
    set port [get_ports aud_$signal]
    if {[llength $start] != 1 || [llength $port] != 1} {error "Missing audio timing endpoint: $signal"}
    # UG835: -reset_path clears all prior exception types for these endpoints.
    # This disposable view disables setup only; minimum timing remains active.
    # Never write this view as an accepted checkpoint or bitstream.
    set_false_path -setup -reset_path -from $start -to $port
    set_min_delay 0.0 -from $start -to $port
    report_timing -from $start -to $port -delay_type min -max_paths 4 \
        -path_type full_clock_expanded -file [file join $reports [format "%s_min.rpt" $signal]]
}
puts "AUDIO_EARLY_AUDIT_ONLY_NO_CHECKPOINT_WRITTEN"
