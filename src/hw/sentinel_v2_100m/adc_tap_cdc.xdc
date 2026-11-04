# adc_tap status flags cross from AD9361 receive clock to 100 MHz DSP clock.
# The first D pin of each two-flop synchronizer is a genuine asynchronous
# CDC endpoint; the second stage and ordinary data paths remain fully timed.
set status_sync_first [get_pins -hier -regexp {.*adc_tap_0/inst/(overflow_sync_reg\[0\]|mismatch_sync_reg\[0\])/D}]
set_false_path -to $status_sync_first

# v2 uses XPM_CDC_ASYNC_RST in each domain and a write-clock registered
# FIFO reset. No reset recovery path is masked by this XDC.
