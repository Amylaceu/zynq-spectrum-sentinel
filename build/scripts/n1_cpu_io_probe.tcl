connect -url tcp:localhost:3121
puts "N1_CPU_AND_IO_PROBE"
targets -set -filter {name =~ "ARM*#0"}
if {[catch {
    stop
    puts [rrd pc]
    puts [rrd cpsr]
} message]} {puts "CPU_PROBE_ERROR $message"}
if {[catch {con} message]} {puts "RESUME_ERROR $message"}
targets -set -filter {name == "APU"}
foreach address {0xF8000738 0xF800073C 0xF8000154 0xE0000000 0xE0000004 0xE0000018 0xE000002C 0xE0000034} {
 if {[catch {puts [mrd -force $address 1]} message]} {puts "IO_READ_ERROR $address $message"}
}
disconnect
exit
