connect -url tcp:localhost:3121
puts "N1_JTAG_TARGETS_BEGIN"
targets
puts [targets]
if {[catch {
    targets -set -filter {name == "APU"}
    puts "N1_BOOT_MODE_REGISTER"
    puts [mrd -force 0xF800025C 1]
} message]} {puts "N1_READ_ONLY_PROBE_ERROR $message"}
disconnect
exit
