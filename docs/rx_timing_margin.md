# RX digital timing margin — 2026-11-02

The receive-only diagnostic uses the pinned no-OS register definitions and AXI ADC PN9 checker, following the existing timing-analysis concepts in `ad9361_conv.c`. The project's wrapper intentionally does not call the official full timing-analysis helper, whose cleanup unmutes TX; TX remains muted throughout this diagnostic.

At each of256clock/data delay combinations, the wrapper enters ALERT, writes AD9361 register0x006, returns to RX, settles5ms, clears all four sticky PN_ERR/PN_OOS flags and observes10ms. ADC valid state must also be set. Error mask0x06 indicates PN error/out-of-sync;0x100 marks absent valid state. A passing point is all-zero combined status, not a measured bit-error rate.

| Sample rate | Passing points /256 | Data-axis contiguous window at original clock | Clock-axis window at original data |
|---|---:|---:|---:|
|30.72MSPS |145 |13codes |4codes |
|3.84MSPS |153 |16codes |4codes |

For both rates, the original register was0x02 (clock code0,data code2). Both scans restored exactly0x02; subsequent500ms PRBS checks returned four zero channel statuses. Both TX attenuations read89750mdB. Test close asserted RF reset and read GPIO0. The numerical contiguous-window criterion of at least3codes passed. No calibration value was selected or permanently changed.

The displayed windows apply only to these two sample rates and the current setup. They are bounded code-space observations, not nanosecond eye-width measurements, long-duration BER guarantees or per-lane FPGA IDELAY qualification. Other G2 requirements, TX-DMA bit-exact loopback and full control API remain open.

Before compiling, the active LCD receive process was terminated gracefully and confirmed exited. The new wrapper compiled on the ARM board with unresolved-symbol checking; exit0. Existing no-OS unused-parameter and board-clock skew warnings were retained. No shared library was overwritten while it was mapped by a live RF process. No vendor/third-party source edits or bitstream rebuild occurred.

After scanning, restarted the existing sharp-font live LCD application; its runtime evidence is stored separately as `board/measurements/lcd_after_timing.json`. The900second runtime limit and RX-only behavior remain unchanged.

Evidence: `board/measurements/rx_timing_margin.json`, `report/figures/rx_timing_margin.png`; validation `tools/analyze_rx_timing.py`. Logs: `logs/P5.3_rx_timing_scan.log`, `logs/P5.3_timing_compile.log`. Sources: `src/ps/libad9361_pynq/app/ad9361_api_c.c`, `board/scripts/scan_rx_timing.py`.
