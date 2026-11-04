# SPDX-License-Identifier: ADIBSD
# Z20 overlay; referenced ADI files remain unchanged.
source [file join [file dirname [info script]] z20_system_bd.tcl]
source [file join [file dirname [info script]] fmcomms2_z20_bd.tcl]
source $ad_hdl_dir/projects/scripts/adi_pd.tcl

ad_ip_parameter axi_sysid_0 CONFIG.ROM_ADDR_BITS 9
ad_ip_parameter rom_sys_0 CONFIG.PATH_TO_FILE "$mem_init_sys_file_path/mem_init_sys.txt"
ad_ip_parameter rom_sys_0 CONFIG.ROM_ADDR_BITS 9
sysid_gen_sys_init_file

# Initial value only; board interface tuning is required at G2.
ad_ip_parameter axi_ad9361 CONFIG.ADC_INIT_DELAY 23
ad_ip_parameter axi_ad9361 CONFIG.TDD_DISABLE 1
