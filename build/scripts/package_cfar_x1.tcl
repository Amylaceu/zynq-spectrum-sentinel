if {![info exists ::env(REPO)]} {error "Initialize tools/env.ps1"}
set root [file normalize $::env(REPO)]
set out [file join $root build work x1_packaged_ip cfar_core_x1]
if {[file exists $out]} {error "Preserve existing X1 package; inspect before rebuilding"}
create_project -in_memory -part xc7z020clg484-2
add_files [glob [file join $root src rtl cfar_x1 *.v]]
add_files [list [file join $root src rtl cfar cfar_occupancy.v] [file join $root src rtl common axis_broadcast2.v]]
set memory [file join $root data reference spectrum spec_log_mantissa.hex]
add_files -norecurse $memory
set_property file_type {Memory Initialization Files} [get_files $memory]
set_property top cfar_core_x1 [current_fileset]
update_compile_order -fileset sources_1
ipx::package_project -root_dir $out -vendor sentinel.org -library user -taxonomy /Sentinel -import_files -set_current true
set core [ipx::current_core]
ipx::infer_bus_interfaces xilinx.com:interface:axis_rtl:1.0 $core
ipx::infer_bus_interfaces xilinx.com:interface:aximm_rtl:1.0 $core
set_property description {X1 CA/GO/SO detection, 16 hard mask intervals, minimum width, strongest-32 targets and coherent frame metadata; integrated simulation verified; board acceptance pending} $core
set clock [ipx::get_bus_interfaces aclk -of_objects $core]
if {[llength $clock]!=1} {error "Missing X1 clock"}
foreach {parameter value} {FREQ_HZ 150000000 ASSOCIATED_BUSIF s_axis_pwr:m_axis_thr:m_axis_hit:m_axis_tgt:s_axi ASSOCIATED_RESET aresetn} {
    set item [ipx::get_bus_parameters $parameter -of_objects $clock]
    if {![llength $item]} {set item [ipx::add_bus_parameter $parameter $clock]}
    set_property value $value $item
}
set_property core_revision 2 $core
ipx::create_xgui_files $core
ipx::update_checksums $core
ipx::check_integrity $core
ipx::save_core $core
puts "X1_CFAR_PACKAGE_PASS"
