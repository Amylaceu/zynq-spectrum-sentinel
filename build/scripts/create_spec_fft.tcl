if {![info exists ::env(REPO)]} {error "Set REPO using tools/env.ps1"}
set root [file normalize $::env(REPO)]
set work [file join $root build work spec_front]
if {[file exists [file join $work spec_front.xpr]]} {
    error "Project already exists; inspect it before resuming instead of overwriting"
}
create_project spec_front $work -part xc7z020clg484-2
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
create_ip -name xfft -vendor xilinx.com -library ip -version 9.1 -module_name spec_fft_2048
set_property -dict [list \
    CONFIG.transform_length {2048} \
    CONFIG.implementation_options {pipelined_streaming_io} \
    CONFIG.data_format {fixed_point} \
    CONFIG.input_width {16} \
    CONFIG.phase_factor_width {18} \
    CONFIG.scaling_options {scaled} \
    CONFIG.rounding_modes {convergent_rounding} \
    CONFIG.output_ordering {natural_order} \
    CONFIG.throttle_scheme {nonrealtime} \
    CONFIG.aresetn {true} \
    CONFIG.ovflo {true}] [get_ips spec_fft_2048]
generate_target all [get_ips spec_fft_2048]
export_ip_user_files -of_objects [get_ips spec_fft_2048] -no_script -sync
report_property [get_ips spec_fft_2048] -file [file join $root logs N2_fft_properties.log]
export_simulation -of_objects [get_ips spec_fft_2048] -simulator xsim \
    -directory [file join $work fft_sim] -export_source_files -force
puts "N2_FFT_IP_GENERATION_PASS"
close_project
