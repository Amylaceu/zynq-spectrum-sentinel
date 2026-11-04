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
