source ../../../scripts/adi_env.tcl
source $ad_hdl_dir/projects/scripts/adi_project_xilinx.tcl
set sys_zynq 1
set ADI_POST_ROUTE_SCRIPT [file normalize $ad_hdl_dir/projects/scripts/auto_timing_fix_xilinx.tcl]
open_project fmcomms2_z20_lcd.xpr
foreach run [get_runs -filter {IS_SYNTHESIS == 1}] {
    puts "RUN_STATE $run [get_property STATUS $run] [get_property PROGRESS $run]"
    if {[get_property PROGRESS $run] ne "100%" || [string match -nocase *error* [get_property STATUS $run]]} {
        reset_run $run
        launch_runs $run -jobs 1
        wait_on_run $run
    }
}
open_run synth_1
report_timing_summary -file timing_synth.log
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
set_property STEPS.ROUTE_DESIGN.TCL.POST $ADI_POST_ROUTE_SCRIPT [get_runs impl_1]
launch_runs impl_1 -to_step write_bitstream
wait_on_run impl_1
open_run impl_1
report_timing_summary -file timing_impl.log
set setup_slack [get_property SLACK [get_timing_paths -setup -max_paths 1]]
set hold_slack [get_property SLACK [get_timing_paths -hold -max_paths 1]]
if {$setup_slack < 0 || $hold_slack < 0} {error "TIMING_FAILED setup=$setup_slack hold=$hold_slack"}
file mkdir fmcomms2_z20_lcd.sdk
write_hw_platform -fixed -force -include_bit -file fmcomms2_z20_lcd.sdk/system_top.xsa
puts "RF_LCD_BUILD_PASS setup=$setup_slack hold=$hold_slack"
source $ad_hdl_dir/library/axi_ad9361/axi_ad9361_delay.tcl
