# Repackage only clock metadata of unchanged RTL IPs for the 100 MHz v2 BD.
# Source packages and accepted v1d builds stay immutable; v1.1 supersedes v1.0.
if {![info exists ::env(REPO)]} {error "Initialize tools/env.ps1 first"}
set root [file normalize $::env(REPO)]
set output [file join $root build work v2_clock_packaged_ip]
set entries {
    {n4_packaged_ip_round2 src_mux aclk}
    {packaged_ip_round2 spec_front aclk}
    {n4_packaged_ip_round2 perf_mon aclk}
    {x5_packaged_ip lcd8080_engine_x5 dsp_clk}
}
foreach entry $entries {
    lassign $entry repository name clock_name
    set original [file join $root build work $repository $name]
    set target [file join $output $name]
    if {![file exists [file join $original component.xml]]} {error "Missing source IP: $original"}
    if {[file exists $target]} {error "Preserve existing v2 IP: $target"}
    file mkdir $output
    file copy $original $target
    set core [ipx::open_core [file join $target component.xml]]
    set_property version 1.1 $core
    set clock [ipx::get_bus_interfaces $clock_name -of_objects $core]
    if {[llength $clock] != 1} {error "Expected one $clock_name on $name"}
    set frequency [ipx::get_bus_parameters FREQ_HZ -of_objects $clock]
    if {[llength $frequency] != 1} {error "Expected FREQ_HZ on $name/$clock_name"}
    set_property value 100000000 $frequency
    ipx::update_checksums $core
    ipx::check_integrity $core
    ipx::save_core $core
    puts "Z10_V2_IP_REPACKED $name 1.1 100000000"
    ipx::unload_core $core
}
puts "Z10_V2_CLOCK_IP_PACKAGING_PASS"
