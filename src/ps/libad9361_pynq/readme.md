# Z20 no-OS control adapter

Build on the board with `make`, after copying the pinned no-OS include directory, RF/AXI ADC/DAC sources, SPI/GPIO APIs and alloc/util/mutex utilities to `../../third_party/no-OS`. `board/scripts/compile_ad9361.sh` documents the tested board layout. The original no-OS tree is read-only.

Use only after the verified `bringup_z20_lcd` image and stable product-ID check. `board/scripts/initialize_ad9361.py` validates these prerequisites and records actual hardware readback.

The Linux backend maps only SPI0x41e00000, GPIO0x41200000 and ADI0x79020000..0x7902ffff. It keeps chip select asserted across FIFO chunks, bounds transfer time, and asserts reset on SPI failure or close. A file lock excludes the Python SPI diagnostic. This library is single-threaded; do not reprogram PL, access those MMIO blocks from another process, or use it concurrently from multiple threads.

Receive-only bring-up uses TDD, TX attenuation89750mdB from the initialization parameters, and immediate post-init ALERT. The adapter exposes no TX-enable operation. A complete application driver and sustained RF/DMA acceptance are not yet implemented.
