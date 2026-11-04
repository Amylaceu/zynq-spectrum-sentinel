# One implementation factor only. This procedure does not reset or launch runs.
proc sentinel_apply_power_policy {run mode} {
    if {$mode ni {On Off}} {error "Power optimization mode must be On or Off"}
    set enabled [expr {$mode eq "On"}]
    set_property STEPS.POWER_OPT_DESIGN.IS_ENABLED $enabled $run
    set_property STEPS.POST_PLACE_POWER_OPT_DESIGN.IS_ENABLED $enabled $run
    puts "Z10_POWER_OPTIMIZATION $mode"
}
