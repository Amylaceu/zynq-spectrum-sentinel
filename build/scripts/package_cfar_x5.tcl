if {![info exists ::env(REPO)]} {error "Initialize tools/env.ps1"}
set root [file normalize $::env(REPO)]
set out [file join $root build work x5_cfar_packaged_ip cfar_core_x5]
if {[file exists $out]} {error "Preserve existing X5 CFAR package"}
create_project -in_memory -part xc7z020clg484-2
add_files [glob [file join $root src rtl cfar_x5 *.v]]
foreach relative {src/rtl/cfar_x1/cfar_detect_x1.v src/rtl/cfar_x1/cfar_x1_regs.v
    src/rtl/cfar/cfar_occupancy.v src/rtl/common/axis_broadcast2.v} {
    add_files [file join $root $relative]
}
set memory [file join $root data reference spectrum spec_log_mantissa.hex]
add_files -norecurse $memory
set_property file_type {Memory Initialization Files} [get_files $memory]
set_property top cfar_core_x5 [current_fileset]
update_compile_order -fileset sources_1
ipx::package_project -root_dir $out -vendor sentinel.org -library user -taxonomy /Sentinel -import_files -set_current true
set core [ipx::current_core]
ipx::infer_bus_interfaces xilinx.com:interface:axis_rtl:1.0 $core
ipx::infer_bus_interfaces xilinx.com:interface:aximm_rtl:1.0 $core
set_property description {X5 CFAR: registered config, elastic masked bins, carry-save saturated clustering; X1 MMIO/numeric compatible} $core
set clock [ipx::get_bus_interfaces aclk -of_objects $core]
if {[llength $clock]!=1} {error "Missing X5 CFAR clock"}
foreach {parameter value} {FREQ_HZ 150000000 ASSOCIATED_BUSIF s_axis_pwr:m_axis_thr:m_axis_hit:m_axis_tgt:s_axi ASSOCIATED_RESET aresetn} {
    set item [ipx::get_bus_parameters $parameter -of_objects $clock]
    if {![llength $item]} {set item [ipx::add_bus_parameter $parameter $clock]}
    set_property value $value $item
}
set_property core_revision 1 $core
ipx::create_xgui_files $core
ipx::update_checksums $core
ipx::check_integrity $core
ipx::save_core $core
puts "X5_CFAR_PACKAGE_PASS"
