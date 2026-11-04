# Isolated IP-generation probe. Never opens or modifies the live v2 project.
if {![info exists ::env(REPO)]} {error "Initialize tools/env.ps1"}
set directory [file normalize [file join $::env(REPO) build work z10_clock_source_probe]]
if {[file exists $directory]} {error "Preserve previous probe"}
create_project clock_source_probe $directory -part xc7z020clg484-2
create_ip -name clk_wiz -vendor xilinx.com -library ip -module_name dsp_clock_probe
set_property -dict [list CONFIG.PRIM_SOURCE No_buffer CONFIG.PRIM_IN_FREQ 50.000 \
    CONFIG.CLKOUT1_REQUESTED_OUT_FREQ 100.000 CONFIG.USE_RESET true \
    CONFIG.RESET_TYPE ACTIVE_LOW CONFIG.USE_LOCKED true] [get_ips dsp_clock_probe]
generate_target all [get_ips dsp_clock_probe]
report_property [get_ips dsp_clock_probe] -file [file join $directory parameters.txt]
puts "Z10_CLOCK_SOURCE_PROBE_READY $directory"
close_project
