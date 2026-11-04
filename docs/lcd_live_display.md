# J22 live receive display — 2026-11-02

User requested actual receive information on the LCD. The independent `fmcomms2_z20_lcd_live` project retains the verified RF constraints, G22 FMC power enable and original J22 wiring (RD=Y4, RESET=AA4). The original colorbar project/artifacts remain available. No vendor or third-party source was edited.

## Implementation

- AXI BRAM at0x42000000,256KiB; two128KiB pages with400x240 RGB332 pixels, doubled to the800x480 LCD. SSD1963 initialization and bus pulse durations follow the previously verified colorbar controller.
- AXI GPIO control at0x41210000. Output bit0 requests a page; input at offset8 reports signature0x4C43, frame Gray counter, ready bit1 and active page bit0. The page request crosses two synchronizers and is latched only at frame boundary. The CPU waits for acknowledgement before reusing a page.
- Board software captures65536 native I1/Q1/I2/Q2 samples per update through guarded ADI DMA, computes2048-point Hann-window FFT averages on the Cortex-A9, and renders spectrum/waterfall/status using Pillow. Displayed range88–108MHz, LO98MHz, sampling30.72MSPS, RF bandwidth24MHz, RX1 slow AGC.
- Pixel data are dBFS per FFT bin, not externally calibrated dBm. Each waterfall row represents a new snapshot; acquisition has gaps. This is not full-rate continuous FFT processing or the final PL accelerator chain. Neural classification stays paused.
- The launcher runs900seconds, then disables DMA and asserts RF reset, keeping a final `RX STOPPED` display. No startup service has been installed. TX remains muted with both attenuations89750mdB.

## Validation

Computer:25PS tests passed (`logs/P5.4_lcd_pc_all.log`). RTL simulation checks byte lanes, RGB332 conversion,2x pixel duplication and no mid-frame page change: `LCD_PIXEL_AND_PAGE_SWAP_PASS` (`logs/P5.4_lcd_rtl.log`).

First build failed because GPIO default value0 required hexadecimal formatting. Removed an attempted read-only MEM_DEPTH setting as well; memory depth derives from the256KiB address segment. Second build succeeded. Final setup/hold/pulse slacks +0.471/+0.021/+0.264ns, no failing endpoints. Utilization14468LUTs and68/140BRAM tiles. Known ADI2025.1 versus installed2025.2 warning remains. No timing constraints were relaxed.

Board transfer initially failed while host Ethernet was disconnected. User explicitly reconnected GE_PS/power, after link negotiation SSH recovered. All three artifact hashes matched on the board. First application launch stopped before RF initialization because PYNQ places AXI BRAM in `mem_dict`, not `ip_dict`. Inspected actual installed metadata, checked exact address/range, corrected the lookup, then second launch passed.

Ten IDs0x0A, RX-only ENSM and rate/LO checks passed. DMA guards remained intact, page acknowledgement and frame count advanced. Saved checkpoint exceeds100frames at approximately1.67updates/s. User explicitly confirmed the green spectrum, colored waterfall and increasing FRAME number. `board/measurements/lcd_live_preview.png` is the software-rendered board frame, not a photograph. `lcd_live_spectrum.npz` contains actual received spectrum data.

## Saved files / restart

- Source: `src/hw/fmcomms2_z20_lcd_live/`.
- Generated Vivado project: `build/work/adi_hdl/projects/fmcomms2/fmcomms2_z20_lcd_live/fmcomms2_z20_lcd_live.xpr`.
- Artifacts: `board/overlay/live_z20_lcd/` (bit/hwh/xsa, SHA256 and provenance).
- Bit SHA256:773a378a6ee8f4b6b7e9a824e71a4eaa823087f33faf57c2029348f2a92c8487.
- Python display driver/rendering: `src/ps/sentinel/lcd_framebuffer.py`, `lcd_spectrum.py`.
- Board application: `board/scripts/lcd_live_receive.py`; launcher `run_lcd_live.sh`.
- Evidence: `board/measurements/lcd_live_receive.json`, `lcd_live_confirmation.json`; logs `logs/P5.4_lcd_board_round1.log`, `P5.4_lcd_board_round2.log`.

Restart only when no existing RF test/application is running. On the board, use `sudo sh /home/xilinx/sentinel/scripts/run_lcd_live.sh`. The application checks artifact hashes and loads the new image itself; its RF lock prevents a concurrent controller from operating during initialization. Never overwrite the shared library while an application is using it.

P5.4 overall, board headphone output, touch, final hardware DSP chain, classifier and full G2/G3 remain incomplete. Current visual acceptance is limited to this receive display.

## Font revision

User reported ghosted text in the first display. Changed from9px regular/12px title to10px bold/14px title with monochrome glyph coverage, higher-contrast colors and adjusted bottom spacing. All frames are still drawn from a fresh blank image before page swapping. Software previews now explicitly use nearest-neighbor2x scaling to match hardware instead of default interpolated scaling. No new HDL, constraints or bitstream was needed.

Stopped the old receive process with SIGTERM, confirmed exit, updated the Python files and restarted. Four relevant PC tests passed. Board snapshot reached90frames with intact DMA guards; a pixel check on the header contains only foreground/background colors, with no antialias fringe. User explicitly confirmed text is clear and ghosting disappeared. This establishes the revised display's visual acceptance, without proving the original physical cause. Evidence: `lcd_font_confirmation.json`, `lcd_font_preview.png`, `lcd_font_runtime.json`; log `logs/P5.4_lcd_font_acceptance.log`.
