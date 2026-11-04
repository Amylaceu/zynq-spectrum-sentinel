# Export and inspect the repaired candidate. No placement/routing performed.
set root [file normalize $::env(REPO)]
set reports [file join $root build reports sentinel_v2_100m development_export_r2]
if {[file exists $reports]} {error "Preserve prior export r2"}
file mkdir $reports
set_param general.maxThreads 8
open_project [file join $root build work adi_hdl projects fmcomms2 sentinel_v2_100m sentinel_v2_100m.xpr]
open_run impl_1
close_design
open_checkpoint [file join $root build reports sentinel_v2_100m audio_route_repair_r2 repaired.dcp]
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $reports timing.rpt]
report_methodology -file [file join $reports methodology.rpt]
report_exceptions -write_valid_exceptions -file [file join $reports valid_exceptions.xdc]
set fd [open [file join $reports checkpoint_provenance.txt] w]
puts $fd "source audio_route_repair_r2/repaired.dcp"
puts $fd "wns [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]"
puts $fd "whs [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]"
puts $fd "blackbox_count [llength [get_cells -quiet -hier -filter {IS_BLACKBOX == 1}]]"
puts $fd "unsafe_fifo_reset_d_count [llength [get_pins -quiet -hier -regexp {.*adc_tap_0/inst/fifo_reset_reg/D}]]"
close $fd
write_bitstream [file join $reports sentinel_v2_100m.bit]
write_hw_platform -fixed -include_bit -file [file join $reports sentinel_v2_100m.xsa]
# Disposable physical min/max view; never persisted to hardware artifacts.
foreach {signal regex} {
    bclk {.*audio/serializer/phase_reg\[1\]/C}
    lrc {.*audio/serializer/lrck_reg/C}
    dacdat {.*audio/serializer/dacdat_reg/C}
} {
    set start [get_pins -hier -regexp $regex]
    set port [get_ports aud_$signal]
    set_false_path -setup -reset_path -from $start -to $port
    report_timing -from $start -to $port -delay_type min_max -max_paths 8 -nworst 2 \
        -path_type full_clock_expanded -file [file join $reports [format "%s_physical.rpt" $signal]]
}
puts "REPAIRED_EXPORT_READY_CONTENT_VALIDATION_REQUIRED"
