if {![info exists ::env(REPO)]} {error "Initialize tools/env.ps1"}
if {[llength $argv] != 3} {error "Usage: module source_directory frequency_MHz"}
lassign $argv top relative_src mhz
if {![string is double -strict $mhz] || $mhz <= 0} {error "Invalid clock frequency"}
set root [file normalize $::env(REPO)]
set_param general.maxThreads 2
set source [file join $root $relative_src]
set reports [file join $root build reports modules]
file mkdir $reports
create_project -in_memory -part xc7z020clg484-2
set sources [glob -nocomplain $source/*.v [file join $root src rtl common *.v] [file join $root src rtl regs *_regs.v]]
if {$top in {spec_window spec_power spec_welch spec_db}} {
    set sources [list [file join $source ${top}.v]]
}
if {![llength $sources]} {error "No RTL sources"}
read_verilog $sources
set memories [glob -nocomplain [file join $root data reference spectrum spec_window_*.hex] [file join $root data reference spectrum spec_log_mantissa.hex] [file join $root data reference src_mux n4_sine.hex]]
if {[llength $memories]} {
    add_files -norecurse $memories
    set_property file_type {Memory Initialization Files} [get_files $memories]
}
if {$top eq "spec_front"} {
    set fft [file join $root build work spec_front spec_front.srcs sources_1 ip spec_fft_2048 spec_fft_2048.xci]
    if {![file exists $fft]} {error "Generate the verified FFT IP first"}
    read_ip $fft
    synth_ip [get_ips spec_fft_2048]
}
set_property include_dirs [list [file join $root src rtl common]] [current_fileset]
set constraint_dir [file join $root build work module_constraints]
file mkdir $constraint_dir
set xdc [file join $constraint_dir ${top}.xdc]
set handle [open $xdc w]
puts $handle "create_clock -name module_clk -period [expr {1000.0/$mhz}] \[get_ports aclk\]"
puts $handle {set_input_delay -clock module_clk 0 [get_ports -filter {DIRECTION == IN && NAME != aclk}]}
puts $handle {set_output_delay -clock module_clk 0 [get_ports -filter {DIRECTION == OUT}]}
close $handle
read_xdc $xdc
if {[catch {synth_design -top $top -part xc7z020clg484-2 -mode out_of_context} problem]} {
    puts "SYNTH_FAILURE_DETAILS $problem"
    puts $::errorInfo
    error $problem
}
opt_design
place_design
route_design
if {$top eq "cfar_core"} {
    set occ_ram [get_cells -hierarchical -filter {REF_NAME =~ RAMB* && NAME =~ *occupancy*}]
    puts "CFAR_OCCUPANCY_BRAMS [llength $occ_ram]"
    if {[llength $occ_ram] < 2} {error "Occupancy read/write replicas were not implemented in BRAM"}
    puts "CFAR_DSP_CELLS [get_cells -hierarchical -filter {REF_NAME == DSP48E1}]"
}
if {[llength [get_cells -hierarchical -filter {IS_BLACKBOX == 1}]]} {
    error "Unresolved black boxes remain; timing acceptance is invalid"
}
report_utilization -file [file join $reports ${top}_util.rpt]
report_timing_summary -file [file join $reports ${top}_timing.rpt]
set registers [all_registers]
report_timing -delay_type min -from $registers -to $registers -max_paths 3 \
    -file [file join $reports ${top}_internal_hold.rpt]
set hold_path [get_timing_paths -delay_type min -from $registers -to $registers -max_paths 1]
if {![llength $hold_path]} {error "No internal register hold path"}
set hold_slack [get_property SLACK $hold_path]
puts "MODULE_INTERNAL_HOLD $top $hold_slack"
if {$hold_slack < 0} {error "Internal register hold timing fails"}
if {$top eq "spec_front"} {
    set shift_ram [get_cells -hierarchical -filter {REF_NAME =~ RAMB* && NAME =~ *reorder*frame_ram*}]
    puts "FFTSHIFT_BLOCK_RAMS [llength $shift_ram]"
    if {![llength $shift_ram]} {error "FFTshift memory was not implemented in BRAM"}
}
set worst [get_timing_paths -delay_type max -max_paths 1]
if {![llength $worst]} {error "No constrained timing path"}
set slack [get_property SLACK $worst]
write_checkpoint -force [file join $reports ${top}_routed.dcp]
puts "MODULE_WNS $top $slack"
if {$slack < 0} {error "Module misses clock requirement"}
puts "MODULE_SYNTHESIS_PASS $top"
