# Isolated X5 project: never opens or changes the integrated/frozen project.
if {![info exists ::env(REPO)]} {error "Initialize tools/env.ps1"}
set root [file normalize $::env(REPO)]
set work [file join $root build work x5_fft]
if {[file exists [file join $work x5_fft.xpr]]} {error "X5 project exists; inspect before regenerating"}
create_project x5_fft $work -part xc7z020clg484-2
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
create_ip -name xfft -vendor xilinx.com -library ip -version 9.1 -module_name pfb_fft16
set_property -dict [list \
 CONFIG.transform_length {16} \
 CONFIG.implementation_options {pipelined_streaming_io} \
 CONFIG.data_format {fixed_point} \
 CONFIG.input_width {24} \
 CONFIG.phase_factor_width {18} \
 CONFIG.scaling_options {scaled} \
 CONFIG.rounding_modes {convergent_rounding} \
 CONFIG.output_ordering {natural_order} \
 CONFIG.throttle_scheme {nonrealtime} \
 CONFIG.aresetn {true} \
 CONFIG.ovflo {true}] [get_ips pfb_fft16]
generate_target all [get_ips pfb_fft16]
export_ip_user_files -of_objects [get_ips pfb_fft16] -no_script -sync
report_property [get_ips pfb_fft16] -file [file join $root logs X5_fft_properties.log]
puts "X5_FFT_IP_GENERATION_PASS"
close_project
