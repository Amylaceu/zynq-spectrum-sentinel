# Independent RF/LCD bring-up overlay

Derived from ../fmcomms2_z20; the original base remains unchanged.
- Added G22 FMC_PWRGD=1 (Bank35 LVCMOS33). Z20 base sheet15 J31 D1 PG_C2M -> FMCOMMS3 sheet3 PG_FMC -> sheet4 U301 EN pin15.
- Added existing SSD1963 8080 colorbar logic on original J22 wiring; RD=Y4, reset=AA4. LCD uses board 50 MHz L18 clock.
- PS7, AXI addresses, RX/TX logic and 2.5 V FMC I/O constraints otherwise unchanged. RF RESETB stays software-controlled, default low; ENABLE/TXNRX remain low until driver initialization.
- No antenna transmission is enabled by this overlay. Colorbars are a bring-up display, not a framebuffer or touch driver.
- LCD source SHA256 before extraction: 1acfbddca58295ea4026c862668535cd16cef26fd28def308514bddcbc29c8e3
