connect -url tcp:localhost:3121
foreach core {0 1} {
 targets -set -filter "name =~ {ARM*#$core}"
 if {[catch {stop; puts "CORE$core [rrd pc] [rrd lr] [rrd sp]"} message]} {puts "ERROR $message"}
 catch {con}
}
targets -set -filter {name == "APU"}
foreach pair {{0xF8000258 1} {0xFFFFFF00 24} {0xF8006000 2} {0xF8000740 6}} {
 if {[catch {puts [mrd -force [lindex $pair 0] [lindex $pair 1]]} message]} {puts "ERROR $message"}
}
disconnect
exit
