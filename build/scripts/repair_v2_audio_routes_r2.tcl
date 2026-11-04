# Bounded second attempt: reopen the original T5 route, not r1/repaired.dcp.
set root [file normalize $::env(REPO)]
set reports [file join $root build reports sentinel_v2_100m audio_route_repair_r2]
if {[file exists $reports]} {error "Preserve prior repair r2"}
file mkdir $reports
set_param general.maxThreads 8
open_project [file join $root build work adi_hdl projects fmcomms2 sentinel_v2_100m sentinel_v2_100m.xpr]
open_run impl_1
set before [file join $root build reports sentinel_v2_100m audio_route_repair_r1 before.dcp]
if {![file exists $before]} {error "Original T5 route checkpoint is missing"}
set base_wns [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set base_whs [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
puts "AUDIO_R2_ORIGINAL_T5_WNS $base_wns WHS $base_whs"
if {[expr {abs($base_wns-0.210)}] > 0.010 || [expr {abs($base_whs-0.030)}] > 0.010} {
    error "Unexpected starting checkpoint; preserve prior candidate"
}
source [file join $root src hw sentinel_v2_100m audio_edges_y3.xdc]
report_timing_summary -delay_type min_max -file [file join $reports corrected_before_timing.rpt]
set nets [get_nets -of_objects [get_pins -hier -regexp {.*audio/serializer/(phase_reg\[1\]|lrck_reg|dacdat_reg)/Q}]]
if {[llength $nets] != 3} {error "Expected exactly 3 serializer output nets"}
puts "AUDIO_R2_LOCAL_UNROUTE $nets"
route_design -unroute -nets $nets
route_design -preserve
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $reports timing.rpt]
report_route_status -file [file join $reports route_status.rpt]
foreach {signal regex} {
    bclk {.*audio/serializer/phase_reg\[1\]/C}
    lrc {.*audio/serializer/lrck_reg/C}
    dacdat {.*audio/serializer/dacdat_reg/C}
} {
    report_timing -from [get_pins -hier -regexp $regex] -to [get_ports aud_$signal] \
        -delay_type min_max -max_paths 20 -nworst 10 -path_type full_clock_expanded \
        -file [file join $reports [format "%s.rpt" $signal]]
}
write_checkpoint [file join $reports repaired.dcp]
set wns [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set whs [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
puts "AUDIO_R2_WNS $wns WHS $whs"
if {$wns < 0 || $whs < 0} {error "Development timing failed; do not deploy"}
report_drc -file [file join $reports drc.rpt]
report_cdc -details -file [file join $reports cdc.rpt]
report_bus_skew -file [file join $reports bus_skew.rpt]
report_io -file [file join $reports io.rpt]
report_utilization -file [file join $reports utilization.rpt]
write_bitstream [file join $reports sentinel_v2_100m.bit]
puts "AUDIO_R2_CANDIDATE_READY_NOT_ACCEPTED"
