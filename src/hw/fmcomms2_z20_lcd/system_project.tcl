# SPDX-License-Identifier: ADIBSD
source ../../../scripts/adi_env.tcl
source $ad_hdl_dir/projects/scripts/adi_project_xilinx.tcl
source $ad_hdl_dir/projects/scripts/adi_board.tcl
set ADI_POST_ROUTE_SCRIPT [file normalize $ad_hdl_dir/projects/scripts/auto_timing_fix_xilinx.tcl]

# adi_project_create preserves p_device and derives sys_zynq from it.
set p_device xc7z020clg484-2
adi_project fmcomms2_z20_lcd
adi_project_files fmcomms2_z20_lcd [list \
    system_top.v lcd_j22_colorbar.v system_constr.xdc z20_system_constr.xdc lcd_j22.xdc \
    "$ad_hdl_dir/library/common/ad_iobuf.v"]
set_property strategy Congestion_SpreadLogic_high [get_runs impl_1]
adi_project_run fmcomms2_z20_lcd
source $ad_hdl_dir/library/axi_ad9361/axi_ad9361_delay.tcl
