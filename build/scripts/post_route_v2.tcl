# Project-owned wrapper: upstream reads Tcl variables, not environment values.
# Do not edit the ADI checkout. This hook never changes timing exceptions.
if {![info exists ::env(REPO)]} {error "Missing REPO"}
set ADI_AUTOFIX_MAX_ATTEMPTS 2
if {[info exists ::env(ADI_AUTOFIX_MAX_ATTEMPTS)]} {
    set value $::env(ADI_AUTOFIX_MAX_ATTEMPTS)
    if {![string is integer -strict $value] || $value < 0 || $value > 2} {
        error "v2 automatic physical optimization is limited to two passes"
    }
    set ADI_AUTOFIX_MAX_ATTEMPTS $value
}
puts "Z10_AUTOFIX_LIMIT $ADI_AUTOFIX_MAX_ATTEMPTS"
source [file join [file normalize $::env(REPO)] build work adi_hdl projects scripts auto_timing_fix_xilinx.tcl]
