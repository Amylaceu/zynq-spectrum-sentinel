# Standalone X5 OOC synthesis/place/route, independent of main BD/HDL builds.
if {![info exists ::env(REPO)]} {error "Initialize tools/env.ps1"}
set root [file normalize $::env(REPO)]
set work [file join $root build work x5_fft]
set round 1
if {[info exists ::env(X5_ROUND)]} {set round $::env(X5_ROUND)}
if {$round ni {1 2 3}} {error "X5_ROUND must be 1..3"}
set report [file join $root build reports x5_core round$round]
file mkdir $report
set_param general.maxThreads 2
open_project [file join $work x5_fft.xpr]
set iprun [get_runs -quiet pfb_fft16_synth_1]
if {$iprun eq ""} {create_ip_run [get_files -all pfb_fft16.xci]}
if {[get_property PROGRESS [get_runs pfb_fft16_synth_1]] ne "100%"} {
    launch_runs pfb_fft16_synth_1 -jobs 2
    wait_on_run pfb_fft16_synth_1
}
if {[get_property STATUS [get_runs pfb_fft16_synth_1]] ne "synth_design Complete!"} {
    error "XFFT OOC synthesis incomplete"
}
close_project
create_project -in_memory -part xc7z020clg484-2
set_property target_language Verilog [current_project]
read_verilog [file join $root src rtl pfb pfb_os2.v]
read_verilog [file join $root src rtl nco_capture nco_capture.v]
read_verilog [file join $root src rtl nco_capture x5_channel_capture.v]
read_ip [file join $work x5_fft.srcs sources_1 ip pfb_fft16 pfb_fft16.xci]
# $readmemh files resolve in this isolated working directory.
set synthdir [file join $root build work x5_synth]
file mkdir $synthdir
file copy -force [file join $root src rtl pfb x5_pfb_coeff.hex] $synthdir
file copy -force [file join $root src rtl nco_capture x5_nco_sine.hex] $synthdir
cd $synthdir
synth_design -top x5_channel_capture -mode out_of_context -part xc7z020clg484-2
create_clock -name aclk -period 6.666667 [get_ports aclk]
set_clock_uncertainty 0.10 [get_clocks aclk]
set_input_delay 1.0 -clock aclk [get_ports -filter {DIRECTION == IN && NAME != aclk}]
set_output_delay 1.0 -clock aclk [get_ports -filter {DIRECTION == OUT}]
report_utilization -hierarchical -file [file join $report synthesis_utilization.rpt]
report_drc -file [file join $report synthesis_drc.rpt]
write_checkpoint -force [file join $synthdir synthesized.dcp]
opt_design
place_design
route_design
report_utilization -hierarchical -file [file join $report routed_utilization.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $report routed_timing.rpt]
report_drc -file [file join $report routed_drc.rpt]
write_checkpoint -force [file join $synthdir routed.dcp]
set setup [get_timing_paths -delay_type max -max_paths 1]
set hold [get_timing_paths -delay_type min -max_paths 1]
if {[llength $setup]==0 || [llength $hold]==0} {error "Missing timing paths"}
if {[get_property SLACK $setup]<0 || [get_property SLACK $hold]<0} {error "X5 standalone timing failed"}
puts "X5_STANDALONE_150MHZ_PASS"
