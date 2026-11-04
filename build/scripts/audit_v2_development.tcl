# Read-only review of the existing routed candidate; no timing exceptions added.
source [file join $::env(REPO) build scripts audit_sentinel_v2.tcl]
foreach {tag from to} {
    cpu_to_dsp clk_fpga_0 clk_out1_system_dsp_clock_0
    dsp_to_cpu clk_out1_system_dsp_clock_0 clk_fpga_0
    lcd_to_cpu sys_clk clk_fpga_0
} {
    report_timing -from [get_clocks $from] -to [get_clocks $to] \
        -max_paths 2000 -nworst 1 -path_type short \
        -file [file join $reports ${tag}.rpt]
}
report_timing -to [get_ports {lcd_data[*] lcd_rs lcd_cs_n lcd_wr_n lcd_reset_n}] \
    -max_paths 100 -path_type full -file [file join $reports lcd_outputs.rpt]
report_timing -to [get_ports {aud_lrc aud_dacdat}] -delay_type min_max \
    -max_paths 20 -file [file join $reports audio_outputs.rpt]
puts "V2_DEVELOPMENT_REVIEW_REPORTS_READY"
