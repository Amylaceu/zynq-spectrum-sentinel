# Z10 v2 build runner. Called after adi_project/adi_project_files for a fresh
# project, or after open_project/reset_run impl_1 for implementation-only reuse.
if {![info exists ::env(REPO)]} {error "Initialize tools/env.ps1 first"}
set root [file normalize $::env(REPO)]
set reports [file join $root build reports sentinel_v2_100m]
if {[info exists ::env(SENTINEL_BUILD_TAG)] && $::env(SENTINEL_BUILD_TAG) ne ""} {
    set reports [file join $reports $::env(SENTINEL_BUILD_TAG)]
}
file mkdir $reports
set_param general.maxThreads 8
# Keep completed implementation evidence before resetting changed OOC inputs.
if {[get_property PROGRESS [get_runs impl_1]] ne "0%"} {
    set saved [file join $reports prior_runs impl_1]
    if {[file exists $saved]} {error "Preserve prior implementation evidence: $saved"}
    file mkdir $saved
    set directory [get_property DIRECTORY [get_runs impl_1]]
    foreach pattern {*.log *.rpt *.tcl *.txt *.xml *.dcp *.bit} {
        foreach artifact [glob -nocomplain -directory $directory $pattern] {
            file copy $artifact $saved
        }
    }
}
set impl_only [expr {[info exists ::env(SENTINEL_IMPL_ONLY)] && $::env(SENTINEL_IMPL_ONLY) eq "1"}]
if {$impl_only} {
    # Preserve the completed implementation above BEFORE reset_run deletes it.
    reset_run impl_1
}
if {!$impl_only} {
    if {$ADI_USE_OOC_SYNTHESIS != 1} {error "Z10 requires OOC synthesis and cache"}
    # Module-reference OOC runs do not always report NEEDS_REFRESH after an
    # external HDL edit. Explicitly invalidate the changed module; completed
    # checkpoints for other IP remain available.
    set refresh_adc [expr {[info exists ::env(SENTINEL_REFRESH_ADC)] && $::env(SENTINEL_REFRESH_ADC) eq "1"}]
    set refresh_clocks [expr {[info exists ::env(SENTINEL_REFRESH_CLOCKS)] && $::env(SENTINEL_REFRESH_CLOCKS) eq "1"}]
    # ADI's own project script installs a shared IP cache in build/work/adi_hdl/ipcache.
    # Preserve completed OOC runs. Reset only failed, stale or interrupted
    # synthesis runs, after keeping their evidence outside the run directory.
    set pending {}
    foreach run [get_runs -filter {IS_SYNTHESIS == 1}] {
        set status [get_property STATUS $run]
        set stale [get_property NEEDS_REFRESH $run]
        puts "Z10_RUN_STATE $run status={$status} stale=$stale"
        if {($refresh_adc && $run eq "system_adc_tap_0_0_synth_1") ||
            ($refresh_clocks && $run in {system_dsp_clock_0_synth_1 system_audio_clock_0_synth_1}) ||
            $stale || [regexp -nocase {error|failed|cancelled|Scripts Generated|Running|Queued} $status]} {
            set saved [file join $reports prior_runs $run]
            if {[file exists $saved]} {error "Preserve previous retry evidence: $saved"}
            file mkdir $saved
            set directory [get_property DIRECTORY $run]
            foreach pattern {*.log *.rpt *.tcl *.xml .vivado.error.rst} {
                foreach artifact [glob -nocomplain -directory $directory $pattern] {
                    file copy $artifact $saved
                }
            }
            reset_run $run
        }
        set status [get_property STATUS $run]
        if {![string match {*Complete*} $status] && $status ne "Using cached IP results"} {
            lappend pending $run
        }
    }
    # An external module-reference edit does not reliably dirty synth_1.
    # Rebuild the top netlist after refreshing ADC, while retaining completed
    # OOC checkpoints for every unchanged IP.
    if {$refresh_adc || $refresh_clocks} {
        set top_run [get_runs synth_1]
        if {[string match {*Complete*} [get_property STATUS $top_run]]} {
            set saved [file join $reports prior_runs synth_1]
            if {[file exists $saved]} {error "Preserve previous top synthesis evidence: $saved"}
            file mkdir $saved
            set directory [get_property DIRECTORY $top_run]
            foreach pattern {*.log *.rpt *.tcl *.xml *.dcp} {
                foreach artifact [glob -nocomplain -directory $directory $pattern] {
                    file copy $artifact $saved
                }
            }
            reset_run $top_run
        }
        if {[lsearch -exact $pending $top_run] < 0} {lappend pending $top_run}
    }
    if {[llength $pending]} {launch_runs -jobs 6 {*}$pending}
    wait_on_run synth_1
    puts "Z10_SYNTH_STATUS [get_property STATUS [get_runs synth_1]]"
    if {![string match {*Complete*} [get_property STATUS [get_runs synth_1]]]} {
        error "Z10 synthesis failed; preserve the project and logs"
    }
}
open_run synth_1
report_timing_summary -file [file join $reports synth_timing.rpt]
report_methodology -file [file join $reports synth_methodology.rpt]
report_cdc -file [file join $reports synth_cdc.rpt]
report_utilization -file [file join $reports synth_utilization.rpt]
# Reject a recurrence of the unsafe reset bypass before another full route.
set unsafe_fifo_reset [get_pins -quiet -hier -regexp {.*adc_tap_0/inst/fifo_reset_reg/D}]
if {[llength $unsafe_fifo_reset]} {error "ADC reset bypass still in synthesized netlist; refresh ADC OOC"}
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
set power_mode On
if {[info exists ::env(SENTINEL_POWER_OPTIMIZATION)]} {
    set power_mode $::env(SENTINEL_POWER_OPTIMIZATION)
}
source [file join $root build scripts z10_impl_policy.tcl]
sentinel_apply_power_policy [get_runs impl_1] $power_mode
set hook [file join $root build scripts post_route_v2.tcl]
if {![llength [get_files -quiet $hook]]} {add_files -fileset utils_1 -norecurse $hook}
set_property STEPS.ROUTE_DESIGN.TCL.POST [get_files $hook -of [get_fileset utils_1]] [get_runs impl_1]
launch_runs impl_1 -to_step write_bitstream -jobs 6
wait_on_run impl_1
puts "Z10_IMPL_STATUS [get_property STATUS [get_runs impl_1]]"
if {[get_property STATUS [get_runs impl_1]] ne "write_bitstream Complete!"} {
    error "Z10 implementation did not complete; no deployable bitstream"
}
open_run impl_1
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $reports final_timing.rpt]
report_utilization -file [file join $reports final_utilization.rpt]
report_cdc -file [file join $reports final_cdc.rpt]
report_io -file [file join $reports final_io.rpt]
report_clocks -file [file join $reports final_clocks.rpt]
catch {report_qor_suggestions -file [file join $reports final_qor_suggestions.rpt]} qor_error
catch {report_design_analysis -congestion -file [file join $reports final_congestion.rpt]} congestion_error
puts "Z10_QOR_REPORT $qor_error"
puts "Z10_CONGESTION_REPORT $congestion_error"
set wns [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set whs [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
puts "Z10_FINAL_WNS $wns"
puts "Z10_FINAL_WHS $whs"
if {$wns eq "" || $whs eq "" || $wns < 1.0 || $whs < 0} {
    error "Z10 target not met: WNS >= +1.0 ns and WHS >= 0 ns; do not deploy"
}
set sdk [file join [pwd] sentinel_v2_100m.sdk]
file mkdir $sdk
write_hw_platform -fixed -force -include_bit -file [file join $sdk system_top.xsa]
puts "Z10_V2_TIMING_PASS"
