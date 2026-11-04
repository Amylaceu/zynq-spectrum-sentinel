# RX-injected BIST and DMA acceptance — 2026-11-02

The same `bringup_z20_lcd` image remains loaded. The user confirmed complete LCD colorbars and changing top strip. No image rebuild, pin changes, AMC training, or antenna transmission was performed for this test.

## Actual result

- Fixed no-OS init succeeded; rate30720000samples/s.
- AD9361 internal BIST injects an RX-only complex tone: code0 means rate/32=960000Hz, level12 means -12dB. The C adapter exposes no TX-enable operation.
- Receive-only ENSM mode1 was read back before capture.
- Four independent ADI RX DMA transfers each completed65536bytes:8192 simultaneous RX1/RX2 complex samples per transfer, native order I1,Q1,I2,Q2, signed16 little-endian words containing sign-extended12-bit data.
- Separate CMA allocations were used. Each transfer targeted the middle of a guarded buffer;64-byte leading/trailing canaries remained unchanged. The initial data sentinel cannot explain the accepted tone data.
- Both channels in every transfer peaked at+960000Hz, with dominant-bin power fraction0.9999976514592444. Native range was-512..511 and complex RMS511.9986counts. This confirms clean quadrature and expected tone frequency, not just nonzero memory.
- Host-observed elapsed time was33.69–36.94ms per request, including Python allocation/cache/MMIO overhead. This is not a maximum DMA bus-throughput measurement.
- TX1/TX2 attenuation remained89750mdB. At completion RX BIST was disabled, DMAC CTRL=0 was written and RF reset asserted; GPIO readback0, no retained/in-flight buffers.

Evidence: `board/measurements/rx_bist_round1.json`, `rx_bist_first_native.npy`, `report/figures/rx_bist_capture.png`; log `logs/P5.2_rx_bist_round1.log`. Retrieved first-capture bytes matched SHA256 `7fde875e8b022cb57d664b8cc2903b6d7fe50a3602b50ef5ff978d7b06fd2854`.

The normalized two-channel SigMF pair is `data/captured/samples/rx_bist_verified.sigmf-{data,meta}`. Values are left-aligned to16bits by multiplying native12-bit samples by16. Metadata explicitly labels an internal diagnostic source, not antenna reception or AMC training data.

## Implementation and limits

`board/scripts/capture_rx_bist.py` validates the loaded image and prior stable identity, initializes RF, starts only RX-injected BIST, acquires guarded buffers with the existing `AdiDmac`, and checks both channels against the expected tone. If a DMA request remains unacknowledged on failure, the background process disables DMA/RF and stays alive holding CMA memory until explicit board reset. This quarantine path was not needed in the passing hardware run.

`rx_acceptance.py` also rejects zero data, missing Q, wrong tone frequency and noise in PC tests. An initial new-test import used the board package name instead of the repository namespace; corrected to match the existing tests. All18PS tests passed. PYNQ's installed buffer implementation was inspected to verify sliced physical addresses and allocation ownership. No driver or third-party source change was required for the ADI two-bit transfer ID; the fixed HDL's `axi_dmac_regmap_request.v` explicitly implements2-bit IDs/four completion bits.

Current board shared-library SHA256 after adding the RX-only BIST operation: `64954b2581da584476b0e5bf34c6f46073ec0737d2852c34b97bb3d89f38e2af`. The original initialization-only library hash in the previous checkpoint is historical.

This proves the internal AD9361 receive digital output, FMC receive interface, FPGA receive packing and HP1/DMA-to-DDR path for bounded diagnostic captures. It does not prove RF sensitivity, antenna reception, sustained recording without gaps, TX-DMA bit-exact digital loopback, numerical tuning-window width, software LCD framebuffer, touch, or complete G2 acceptance. Those gates remain open.
