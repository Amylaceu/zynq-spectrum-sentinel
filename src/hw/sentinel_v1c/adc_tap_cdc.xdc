# adc_tap status flags cross from the AD9361 receive clock into the
# 150 MHz DSP clock. Only the first D pin of each two-flop synchronizer
# is asynchronous; the second stage remains fully timed.
set status_sync_first [get_pins -hier -regexp {.*adc_tap_0/inst/(overflow_sync_reg\[0\]|mismatch_sync_reg\[0\])/D}]
set_false_path -to $status_sync_first

# dsp_aresetn is asserted asynchronously into the AD9361 clock domain;
# reset_sync then releases the FIFO reset through three receive-clock flops.
# Exempt only their asynchronous preset pins, not downstream data paths.
set reset_async_preset [get_pins -hier -regexp {.*adc_tap_0/inst/reset_sync_reg\[[0-2]\]/PRE}]
set_false_path -to $reset_async_preset

# Registered Gray source: constrain every bit to the first synchronizer stage.
# 8ns is shorter than the minimum receive-clock period used by these tests.
# Fail closed if hierarchy changes; never false-path the binary counter bus.
set drop_q [get_pins -hier -regexp {.*adc_tap_0/inst/drop_gray_reg\[[0-9]+\]/Q}]
set drop_d [get_pins -hier -regexp {.*adc_tap_0/inst/drop_sync0_reg\[[0-9]+\]/D}]
if {[llength $drop_q]!=32 || [llength $drop_d]!=32} {error "Missing X2 Gray CDC endpoints"}
set_max_delay -datapath_only 8.0 -from $drop_q -to $drop_d
set_bus_skew 8.0 -from $drop_q -to $drop_d
