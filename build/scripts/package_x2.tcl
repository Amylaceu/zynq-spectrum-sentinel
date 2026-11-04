if {![info exists ::env(REPO)]} {error "Initialize tools/env.ps1"}
if {[llength $argv]!=1} {error "Usage: spec_front_x2|cfar_core_x2"}
set ip [lindex $argv 0]
set root [file normalize $::env(REPO)]
set out [file join $root build work x2_packaged_ip $ip]
if {[file exists $out]} {error "Preserve previous X2 package"}
create_project -in_memory -part xc7z020clg484-2
add_files [file join $root src rtl common axis_broadcast2.v]
if {$ip eq "spec_front_x2"} {
    add_files [list [file join $root src rtl x2 spec_front_x2.v] [file join $root src rtl x2 spec_welch_x2.v] \
        [file join $root src rtl regs spec_ctrl_regs.v]]
    foreach name {spec_window spec_power spec_fftshift spec_db spec_display_reduce} {
        add_files [file join $root src rtl spectrum ${name}.v]
    }
    read_ip [file join $root build work spec_front spec_front.srcs sources_1 ip spec_fft_2048 spec_fft_2048.xci]
    set memories [glob [file join $root data reference spectrum spec_window_*.hex] [file join $root data reference spectrum spec_log_mantissa.hex]]
    set buses m_axis_db:m_axis_pwr:s_axis:s_axi
} elseif {$ip eq "cfar_core_x2"} {
    add_files [list [file join $root src rtl x2 cfar_core_x2.v] [file join $root src rtl x2 frame_queue_x2.v] \
        [file join $root src rtl cfar cfar_occupancy.v] [file join $root src rtl spectrum spec_db.v] \
        [file join $root src rtl spectrum spec_display_reduce.v]]
    add_files [glob [file join $root src rtl cfar_x1 *.v]]
    set memories [list [file join $root data reference spectrum spec_log_mantissa.hex]]
    set buses s_axis_pwr:m_axis_db:m_axis_thr:m_axis_hit:m_axis_tgt:s_axi
} else {error "Unknown X2 IP"}
add_files -norecurse $memories
set_property file_type {Memory Initialization Files} [get_files $memories]
set_property top $ip [current_fileset]
update_compile_order -fileset sources_1
ipx::package_project -root_dir $out -vendor sentinel.org -library user -taxonomy /Sentinel -import_files -set_current true
set core [ipx::current_core]
ipx::infer_bus_interfaces xilinx.com:interface:axis_rtl:1.0 $core
ipx::infer_bus_interfaces xilinx.com:interface:aximm_rtl:1.0 $core
set clock [ipx::get_bus_interfaces aclk -of_objects $core]
if {[llength $clock]!=1} {error "Missing X2 clock interface"}
foreach {parameter value} [list FREQ_HZ 150000000 ASSOCIATED_BUSIF $buses ASSOCIATED_RESET aresetn] {
    set item [ipx::get_bus_parameters $parameter -of_objects $clock]
    if {![llength $item]} {set item [ipx::add_bus_parameter $parameter $clock]}
    set_property value $value $item
}
set_property description "X2 $ip: independent source overlay; hardware acceptance required" $core
set_property core_revision 1 $core
ipx::create_xgui_files $core
ipx::update_checksums $core
ipx::check_integrity $core
ipx::save_core $core
puts "X2_PACKAGE_PASS $ip"
