# P5.1 current evidence

- User confirmed original LCD wiring (RD=Y4, RST=AA4), J7/J8=2.5V and no direct TX/RX cable.
- PYNQ SSH and runtime passed before the platform test.
- Vendor DMA HWH exposes only PS DDR/FIXED_IO, no additional PL pads. The J26 RGB example was not used.
- J22 diagnostic was copied from the existing 2.5V backup; bit hash matched d163ee4f5e92159f4e4b05a562e8e4c96c6af7dbfc0649c00148fbc2336e072a. RTL/XDC copied unchanged.
- Remote notebook execution was started with the configured PYNQ Python and authenticated sudo. During execution the Ethernet target stopped answering SSH and ARP.
- No executed notebook or measurements JSON has been retrieved. It is not known which cell completed. DMA pass or CPU timing values must not be inferred.
- User reported power LED on and LCD color bands visible. Top-region animation is not yet confirmed; this observation does not identify which bitstream was last downloaded.
- Windows now lists Bluetooth serial ports only. Attempt to open the historical COM5 failed because the port does not exist; no UART bytes reached the board.
- Stopped the stalled local SSH client, requested USB_UART connection, and stopped additional downloads. The cause of network loss is UNKNOWN, not diagnosed as FPGA/AD9361 damage.
- The unexecuted source notebook remains useful for review; require serial diagnosis before retrying hardware execution.

## Recovery and measured results (2026-11-02)

- User connected USB_UART: CH340 initially COM11; after complete power cycle it enumerated as COM12. PS_TX/PS_RX selection was confirmed.
- After reboot, SSH 192.168.2.99 and Linux UART shell both recovered. The previous-boot journal was retrieved; no definitive fault cause has been established from it. This is not evidence of hardware damage.
- CPU-only notebook executed successfully under authenticated sudo because the vendor Jupyter template directory is not readable by the normal account. No system permissions were relaxed.
- Executed notebook: board/notebooks/test_00_cpu_baseline_executed.ipynb. Machine-readable data: board/measurements/p5_cpu_baseline.json. FFT2048 median 0.67431ms / 1482.997 frames/s; CFAR2048 median 11.95167ms; Pillow800x480 median 6.79426ms.
- Full platform notebook is now guarded by HARDWARE_VALIDATED=False; it must not be run blindly while the interrupted vendor DMA/LCD test remains unresolved.
- A separate, staged base_z20 probe successfully parsed metadata, downloaded the new base image, and read AXI SYSID=0x10161, axi_ad9361 version=0xa0300, control GPIO=0, SPI status=0x25. Network remained accessible afterwards.
- This validates the new base PL image's AXI access only. It is not an AD9361 chip product-ID read, DMA completion, RF initialization, or full-system acceptance. The current base image keeps RF reset asserted by GPIO default 0 and does not enable TX.
- PYNQ warned that axi_iic 2.1 does not have an exact built-in 2.0 driver match; the probe did not force version ignoring or access that IIC peripheral.
