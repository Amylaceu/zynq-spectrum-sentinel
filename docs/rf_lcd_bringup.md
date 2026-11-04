# RF/LCD bring-up checkpoint — 2026-11-02

User priority: pause AMC training and bring up AD9361 with the existing J22 LCD.
Hardware remains ATK Z20, FMCOMMS3, J7/J8=2.5V, original SSD1963 parallel LCD wiring (RD=Y4, RESET=AA4). No TX/RX cable, attenuator, or antenna transmission was used.

## Fixed omission

The original repository base overlay did not drive G22 FMC_PWRGD. The previous standalone successful design did. Local schematic tracing verifies:

1. Z20 base schematic sheet15: FPGA net FMC_PWRGD reaches J31 D1 PG_C2M.
2. FMCOMMS3 RevA sheet3: P201 D1 becomes PG_FMC.
3. FMCOMMS3 sheet4: PG_FMC drives U301 ADP2164 EN pin15, enabling the mezzanine 1.8V regulator and downstream supply sequence.

First base-image SPI acceptance returned ten `0x00` values. The independent corrected image returned ten `0x0A` values. Other base RF constraints, SPI controller ratio/mode and AXI addresses were retained; the corrected image also adds the LCD colorbar. This supports the missing power-good enable as the cause of this repository's zero-ID result; it does not retrospectively diagnose all earlier projects or intermittent failures.

## Saved project and artifacts

- Editable overlay: `src/hw/fmcomms2_z20_lcd/`.
- Generated Vivado2025.2 project: `build/work/adi_hdl/projects/fmcomms2/fmcomms2_z20_lcd/fmcomms2_z20_lcd.xpr`.
- Device/top: `xc7z020clg484-2`, `system_top`.
- Constraints: `system_constr.xdc`, `z20_system_constr.xdc`, `lcd_j22.xdc`.
- Exported bit/hwh/xsa: `board/overlay/bringup_z20_lcd/`; checksums and original generation provenance included.
- Bit SHA256: `dabcf3000b8cf7cd16fffee56db7bea43ad7b132b6353c2409d0229582d75658`.
- Final timing: setup +0.589ns, hold +0.016ns, pulse width +0.264ns, zero failing endpoints. Use `build/reports/bringup_z20_lcd/timing_impl.log` for final post-fix timing; the routed RPT is the earlier pre-fix snapshot.
- All79 explicitly assigned PL pads are unique. No MCU, LCD, or audio pin remapping was introduced. The original base and old successful backups remain intact.

The source contains PS7, the ADI RF interface, software GPIO/QuadSPI and a standalone LCD colorbar. It does not yet contain custom signal-processing IP, a PS framebuffer for this LCD, or a touch driver.

## Actual board results

1. Exported artifact SHA256s verified on the board; PYNQ downloaded the corrected image.
2. SPI mode1, command `00 37 00`: ten consecutive product IDs `0x0A`; identity mask `(value & 0xF8)==0x08` passed. Evidence: `board/measurements/ad9361_product_id_bringup_z20_lcd.json`.
3. Fixed no-OS source compiled as a Linux-userspace shared library with undefined-symbol checking. `ad9361_init` and its AXI ADC/digital-interface setup returned success. Log: `logs/P5.3_initialize_round1.log`.
4. Readback: RX sample rate30720000Hz, productID0x0A, ENSM mode2(ALERT), TX1/TX2 attenuation89750mdB. Evidence: `board/measurements/ad9361_initialization.json`.
5. After acceptance, the control library closed and GPIO was read back as0: RF RESETB asserted, ENABLE/TXNRX low. LCD logic remains running in the PL image. No RF data capture or full G2 acceptance is claimed.
6. LCD visual acceptance passed: the user explicitly confirmed complete colorbars and continuously changing top strip. Evidence: board/measurements/lcd_bringup_confirmation.json. This does not validate a software framebuffer or touch.

## Reproduction and current limitations

`tools/build_rf_lcd.ps1` builds the independent overlay; `-Resume -Attempt 3` can resume the saved project's unfinished synthesis tasks. This build completed on the third execution: first OOC startup failed, then the second resume launcher incorrectly tried already completed runs. The final successful route used ADI's existing hold-fix hook. No constraints were weakened. Initial collection under Windows PowerShell could not autoload Get-FileHash; collection succeeded under the current PowerShell host without rebuilding.

Board scripts: `read_ad9361_product_id.py --overlay bringup_z20_lcd --download`, then `initialize_ad9361.py`. Both require the configured PYNQ interpreter and administrator privileges. Only the first script loads an image. Initialization requires the matching image's stable identity JSON and always closes into reset.

Library sources: `src/ps/libad9361_pynq/`; compiled board .so SHA256 `76343485b898a2bd55c4dde2e95e7731288b6cd5ee5011920a2582be96f9515b`. The public adapter currently exposes receive-only initialization and diagnostic readback, not the complete P5.3 tuning/control API. No TX-enable API is exposed. The default parameter table is derived from the pinned ADI main.c with its license retained; third_party and vendor are untouched.

Network troubleshooting used COM12 without DTR/RTS, followed by the user's confirmed cold reboot. Linux booted and eth0 retained192.168.2.99; explicitly binding SSH to host Ethernet192.168.2.10 restored access. The prior outage's root cause remains unproven. The board clock predates source timestamps, causing make clock-skew warnings; compilation nevertheless exited0 with no unresolved symbols. The known PYNQ IIC2.1/driver2.0 warning remains; that peripheral was not used or forced to ignore versions.

Subsequent bounded RX-injected BIST/DMA acceptance passed; see docs/rx_bist_dma_acceptance.md. P5.1/P5.2/P5.3 remain in progress: vendor-loopback notebook evidence, sustained/bit-exact tests, antenna reception, full control APIs and LCD framebuffer/display integration are outstanding. AMC remains paused.

Antenna diagnostic update: see docs/fm_antenna_acceptance.md.95.8MHz shows stable19kHz pilot evidence; a host-side4.03s segmented WAV is ready for listening. LCD spectrum streaming and board headphone output remain pending.
