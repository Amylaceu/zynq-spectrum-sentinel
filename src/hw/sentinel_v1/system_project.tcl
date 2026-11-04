# SPDX-License-Identifier: ADIBSD
source ../../../scripts/adi_env.tcl
source $ad_hdl_dir/projects/scripts/adi_project_xilinx.tcl
source $ad_hdl_dir/projects/scripts/adi_board.tcl
set ADI_POST_ROUTE_SCRIPT [file normalize $ad_hdl_dir/projects/scripts/auto_timing_fix_xilinx.tcl]
set p_device xc7z020clg484-2
# Module references must be available before adi_project sources system_bd.tcl.
# adi_project_create adds system_top.v automatically, so put references on its pre-BD files hook.
set custom_hdl [list [file normalize $::env(REPO)/src/rtl/adc_tap/adc_tap.v] \
    [file normalize $::env(REPO)/src/rtl/common/sentinel_capture.v] \
    [file normalize $::env(REPO)/src/rtl/common/sentinel_events.v]]
set ::env(SENTINEL_REFERENCE_FILES) $custom_hdl
adi_project sentinel_v1
adi_project_files sentinel_v1 [concat [list system_top.v system_constr.xdc z20_system_constr.xdc lcd_j22.xdc adc_tap_cdc.xdc \
    "$ad_hdl_dir/library/common/ad_iobuf.v"] $custom_hdl]
set_property XPM_LIBRARIES {XPM_CDC XPM_FIFO} [current_project]
set_property strategy Performance_ExplorePostRoutePhysOpt [get_runs impl_1]
if {[info exists ::env(SENTINEL_VALIDATE_ONLY)] && $::env(SENTINEL_VALIDATE_ONLY) eq "1"} {
    validate_bd_design
    save_bd_design
    generate_target all [get_files system.bd]
    puts "SENTINEL_BD_VALIDATION_PASS"
} else {
    adi_project_run sentinel_v1
    source $ad_hdl_dir/library/axi_ad9361/axi_ad9361_delay.tcl
}
