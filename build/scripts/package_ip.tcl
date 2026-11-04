if {![info exists ::env(REPO)]} {error "Initialize tools/env.ps1"}
if {[llength $argv] != 3} {error "Usage: ip_name source_directory output_repository"}
lassign $argv ip relative_src relative_out
set root [file normalize $::env(REPO)]
set src [file normalize [file join $root $relative_src]]
set out [file normalize [file join $root $relative_out $ip]]
if {[file exists [file join $out component.xml]]} {error "Existing package: inspect before replacing"}
create_project -in_memory -part xc7z020clg484-2
set_property XPM_LIBRARIES {XPM_CDC XPM_FIFO} [current_project]
add_files [glob $src/*.v]
set extras [glob -nocomplain [file join $root src rtl common *.v] [file join $root src rtl regs *_regs.v]]
if {[llength $extras]} {add_files $extras}
if {$ip eq "lcd8080_engine"} {
    add_files [file join $root src rtl spectrum spec_display_reduce.v]
    add_files [file join $root src rtl common lcd_init_rom.vh]
    set_property include_dirs [list [file join $root src rtl common]] [current_fileset]
}
if {$ip eq "src_mux"} {
    set memory [file join $root data reference src_mux n4_sine.hex]
    add_files -norecurse $memory
    set_property file_type {Memory Initialization Files} [get_files $memory]
}
if {$ip eq "spec_front"} {
    set fft [file join $root build work spec_front spec_front.srcs sources_1 ip spec_fft_2048 spec_fft_2048.xci]
    if {![file exists $fft]} {error "Generate FFT IP first"}
    read_ip $fft
    set memories [glob -nocomplain [file join $root data reference spectrum spec_window_*.hex] [file join $root data reference spectrum spec_log_mantissa.hex]]
    add_files -norecurse $memories
    set_property file_type {Memory Initialization Files} [get_files $memories]
}
if {$ip eq "cfar_core"} {
    set memory [file join $root data reference spectrum spec_log_mantissa.hex]
    add_files -norecurse $memory
    set_property file_type {Memory Initialization Files} [get_files $memory]
}
proc sentinel_clock {name hz interfaces reset} {
    set clock [ipx::get_bus_interfaces $name -of_objects [ipx::current_core]]
    if {[llength $clock] != 1} {error "Missing clock interface $name"}
    foreach {parameter value} [list FREQ_HZ $hz ASSOCIATED_BUSIF $interfaces ASSOCIATED_RESET $reset] {
        set item [ipx::get_bus_parameters $parameter -of_objects $clock]
        if {![llength $item]} {set item [ipx::add_bus_parameter $parameter $clock]}
        set_property value $value $item
    }
}
set_property top $ip [current_fileset]
update_compile_order -fileset sources_1
ipx::package_project -root_dir $out -vendor sentinel.org -library user -taxonomy /Sentinel -import_files -set_current true
ipx::infer_bus_interfaces xilinx.com:interface:axis_rtl:1.0 [ipx::current_core]
ipx::infer_bus_interfaces xilinx.com:interface:aximm_rtl:1.0 [ipx::current_core]
if {$ip eq "spec_front"} {
    set core [ipx::current_core]
    set_property description {Fixed-point 2048-bin spectrum front end with FFTshift, Welch averaging, logarithm and 560-pixel display reduction} $core
    set clock [ipx::get_bus_interfaces aclk -of_objects $core]
    foreach {parameter value} {FREQ_HZ 150000000 ASSOCIATED_BUSIF m_axis_db:m_axis_pwr:s_axis:s_axi ASSOCIATED_RESET aresetn} {
        set item [ipx::get_bus_parameters $parameter -of_objects $clock]
        if {![llength $item]} {set item [ipx::add_bus_parameter $parameter $clock]}
        set_property value $value $item
    }
}
if {$ip eq "cfar_core"} {
    set core [ipx::current_core]
    set_property description {Circular CA GO SO detection with threshold display, clustered double-buffered target lists and occupancy counters} $core
    set clock [ipx::get_bus_interfaces aclk -of_objects $core]
    foreach {parameter value} {FREQ_HZ 150000000 ASSOCIATED_BUSIF s_axis_pwr:m_axis_thr:m_axis_hit:m_axis_tgt:s_axi ASSOCIATED_RESET aresetn} {
        set item [ipx::get_bus_parameters $parameter -of_objects $clock]
        if {![llength $item]} {set item [ipx::add_bus_parameter $parameter $clock]}
        set_property value $value $item
    }
}
if {$ip eq "src_mux"} {sentinel_clock aclk 150000000 s_axis_rf:s_axis_replay:m_axis:s_axi aresetn}
if {$ip eq "perf_mon"} {sentinel_clock aclk 150000000 s_axi aresetn}
if {$ip eq "lcd8080_engine"} {
    sentinel_clock aclk 50000000 s_axi aresetn
    sentinel_clock dsp_clk 150000000 s_axis_spec:s_axis_thr dsp_aresetn
}
if {$ip eq "lcd8080_engine"} {
    foreach group [ipx::get_file_groups -of_objects [ipx::current_core]] {set_property dependency {} $group}
}
set_property description "Sentinel $ip verified RTL module" [ipx::current_core]
set_property core_revision 1 [ipx::current_core]
ipx::create_xgui_files [ipx::current_core]
ipx::update_checksums [ipx::current_core]
ipx::check_integrity [ipx::current_core]
ipx::save_core [ipx::current_core]
puts "IP_PACKAGE_PASS $ip"
