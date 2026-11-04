# One bounded local repair. No synth, placement, broad unroute, or +1ns retry.
set root [file normalize $::env(REPO)]
set reports [file join $root build reports sentinel_v2_100m audio_route_repair_r1]
if {[file exists $reports]} {error "Preserve prior repair"}
file mkdir $reports
set_param general.maxThreads 8
open_project [file join $root build work adi_hdl projects fmcomms2 sentinel_v2_100m sentinel_v2_100m.xpr]
open_run impl_1
write_checkpoint [file join $reports before.dcp]
source [file join $root src hw sentinel_v2_100m audio_edges_y3.xdc]
report_timing_summary -delay_type min_max -file [file join $reports corrected_before_timing.rpt]
set nets [get_nets -of_objects [get_pins -hier -regexp {.*audio/serializer/(phase_reg\[1\]|lrck_reg|dacdat_reg)/Q}]]
if {[llength $nets] != 3} {error "Expected exactly 3 serializer output nets"}
puts "AUDIO_LOCAL_UNROUTE $nets"
route_design -unroute -nets $nets
# General timing-driven routing with preservation of all completed routes.
# Do not use route_design -nets (its quick route mode ignores timing).
route_design -preserve
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $reports timing.rpt]
report_route_status -file [file join $reports route_status.rpt]
report_drc -file [file join $reports drc.rpt]
report_cdc -details -file [file join $reports cdc.rpt]
report_bus_skew -file [file join $reports bus_skew.rpt]
report_io -file [file join $reports io.rpt]
report_utilization -file [file join $reports utilization.rpt]
foreach {signal regex} {
    bclk {.*audio/serializer/phase_reg\[1\]/C}
    lrc {.*audio/serializer/lrck_reg/C}
    dacdat {.*audio/serializer/dacdat_reg/C}
} {
    report_timing -from [get_pins -hier -regexp $regex] -to [get_ports aud_$signal] -delay_type min_max -max_paths 20 -nworst 10 -path_type full_clock_expanded -file [file join $reports ${signal}.rpt]
}
write_checkpoint [file join $reports repaired.dcp]
set wns [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set whs [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
puts "AUDIO_LOCAL_REPAIR_WNS $wns WHS $whs"
if {$wns < 0 || $whs < 0} {error "Development timing failed; preserve reports, do not deploy"}
write_bitstream [file join $reports sentinel_v2_100m.bit]
puts "AUDIO_LOCAL_REPAIR_CANDIDATE_READY_NOT_ACCEPTED"
