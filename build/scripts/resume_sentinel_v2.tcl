# Only for implementation strategy/constraints with unchanged synthesized netlist.
if {![info exists ::env(REPO)]} {error "Initialize tools/env.ps1 first"}
set project [file join [file normalize $::env(REPO)] build work adi_hdl projects fmcomms2 sentinel_v2_100m sentinel_v2_100m.xpr]
open_project $project
set continue_build [expr {[info exists ::env(SENTINEL_CONTINUE_BUILD)] && $::env(SENTINEL_CONTINUE_BUILD) eq "1"}]
if {$continue_build} {
    if {[info exists ::env(SENTINEL_REFRESH_CLOCKS)] && $::env(SENTINEL_REFRESH_CLOCKS) eq "1"} {
        # Both MMCMs consume the shared top-level sys_clk. No_buffer removes
        # the generated hierarchical primary-clock redefinitions, leaving
        # sys_clk and the actual MMCM generated clocks fully constrained.
        open_bd_design [get_files system.bd]
        foreach instance {dsp_clock audio_clock} {
            set_property CONFIG.PRIM_SOURCE No_buffer [get_bd_cells $instance]
        }
        validate_bd_design
        save_bd_design
        generate_target all [get_files system.bd]
        close_bd_design [current_bd_design]
        puts "Z10_SHARED_CLOCK_ROOT_UPDATED"
    }
    # ValidateOnly generated the BD and output products but intentionally did
    # not synthesize. Reuse the same project and its IP cache without deleting it.
    set ADI_USE_OOC_SYNTHESIS 1
    set ADI_POST_ROUTE_SCRIPT [file normalize [file join [file normalize $::env(REPO)] build work adi_hdl projects scripts auto_timing_fix_xilinx.tcl]]
    source [file join [file normalize $::env(REPO)] build scripts run_sentinel_v2.tcl]
    return
}
if {![string match {*Complete*} [get_property STATUS [get_runs synth_1]]]} {
    error "synth_1 is not complete; implementation-only reuse is forbidden"
}
set report_dir [file join [file normalize $::env(REPO)] build reports sentinel_v2_100m]
file mkdir $report_dir
if {[info exists ::env(SENTINEL_REFERENCE_DCP)] && $::env(SENTINEL_REFERENCE_DCP) ne ""} {
    set reference [file normalize $::env(SENTINEL_REFERENCE_DCP)]
    if {![file exists $reference]} {error "Missing reference checkpoint: $reference"}
    set_property incremental_checkpoint $reference [get_runs impl_1]
    puts "Z10_INCREMENTAL_REFERENCE $reference"
}
# The runner archives the previous implementation before resetting it.
set ::env(SENTINEL_IMPL_ONLY) 1
source [file join [file normalize $::env(REPO)] build scripts run_sentinel_v2.tcl]
