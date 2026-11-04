if {![info exists ::env(SENTINEL_REFERENCE_FILES)]} {error "Missing reference HDL list"}
add_files -norecurse $::env(SENTINEL_REFERENCE_FILES)
update_compile_order -fileset sources_1
# New independent overlay. Custom IP catalog is available before sourcing the BD.
set bd_file [get_files system.bd]
save_bd_design
close_bd_design [current_bd_design]
set extra_repositories [list [file normalize $::env(REPO)/build/work/packaged_ip_round2] \
    [file normalize $::env(REPO)/build/work/n3_packaged_ip_round2] \
    [file normalize $::env(REPO)/build/work/n4_packaged_ip_round2]]
set_property ip_repo_paths [concat [get_property ip_repo_paths [current_fileset]] $extra_repositories] [current_fileset]
update_ip_catalog
open_bd_design $bd_file
source [file join [file dirname [info script]] z20_system_bd.tcl]
source [file join [file dirname [info script]] fmcomms2_z20_bd.tcl]
source $ad_hdl_dir/projects/scripts/adi_pd.tcl
ad_ip_parameter axi_sysid_0 CONFIG.ROM_ADDR_BITS 9
ad_ip_parameter rom_sys_0 CONFIG.PATH_TO_FILE "$mem_init_sys_file_path/mem_init_sys.txt"
ad_ip_parameter rom_sys_0 CONFIG.ROM_ADDR_BITS 9
sysid_gen_sys_init_file
ad_ip_parameter axi_ad9361 CONFIG.ADC_INIT_DELAY 23
ad_ip_parameter axi_ad9361 CONFIG.TDD_DISABLE 1
source [file join [file dirname [info script]] sentinel_bd.tcl]
