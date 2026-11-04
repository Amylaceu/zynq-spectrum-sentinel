# X5 PL interface (DEC=1 baseline)

Integration contract for `pfb_os2` and `nco_capture`. All ports are synchronous to
`aclk=150 MHz`; `aresetn` is active low, sampled on the rising edge. No internal
CDC is provided. Drive GPIO and both AXIS interfaces from this clock domain.
Reset for at least 16 clocks (also resets the official XFFT core).

## PFB

`src/rtl/pfb/pfb_os2.v`: AXIS input `s_axis_tdata[31:0]`, `tvalid`,
`tready`; IQ = `{Q[15:0], I[15:0]}` (signed two's complement). Input has no
TLAST: replay packet boundaries must not reset channelizer history.
Output `m_axis_tdata[31:0]`, `m_axis_tuser[3:0]`, `tvalid`, `tready`,
`tlast`; natural bins 0..15; TLAST only on bin 15. `error_sticky` reports
FFT overflow/framing faults. Reset history, rotation and FFT together when
changing source/rate or restarting a replay sequence.

M=16, D=8, eight taps/phase. Frame zero ends at input sample zero, then at
8,16,...; prehistory is zero. Frame zero is intentionally transient.
Input accepts independently while the time-multiplexed FIR runs, except that
a new frame endpoint is backpressured until the previous FFT input frame has
been handed off. AXIS sources MUST honor ready; a physical ADC requires the
existing FIFO/drop accounting upstream. Intended rate: 3.84 MSPS, channel
rate 480 kSPS. No 30.72 MSPS guarantee. Downstream must normally drain bins;
unbounded backpressure can eventually reach the source.

FFT dependency: generated `pfb_fft16` official AMD XFFT 9.1, 16-point,
pipelined streaming, 24-bit input/output, 18-bit twiddles, natural order,
scaled, convergent rounding, nonrealtime, config `8'h15` (forward;
two radix-4 stages each shift two bits). FIR uses signed18 Q1.17 taps,
signed40 accumulator, arithmetic >>9 into FFT. FFT output arithmetic >>4
then saturate16 matches `sim/golden/pfb.py:pfb_os2_fixed`.

## Capture

`src/rtl/nco_capture/nco_capture.v` input uses the PFB AXIS ports including
TUSER and TLAST. Input ready stays asserted; inactive/unselected bins drain.
The core buffers the complete capture before emitting a DMA packet. DMA
backpressure therefore cannot create holes within an accepted capture.

Config pins: `arm_toggle`, `clear_errors`, `cfg_ch_sel[3:0]`,
`cfg_fcw[31:0]`, `cfg_dec[3:0]`, `cfg_len[12:0]`, `cfg_src[31:0]`,
`timestamp[63:0]`. Status: `busy`, `done_toggle`, `error_sticky[3:0]`,
`captured_count[12:0]`. Output AXIS: `m_axis_tdata[31:0]`,
`m_axis_tkeep[3:0]=4'hf`, `tvalid`, `tready`, `tlast`.

ARM protocol: after reset ARM=0. Hold configuration stable at least two
aclk cycles before changing ARM level. A level change while idle latches
all config. Capture starts at the next selected-bin handshake, with phase=0;
the timestamp is latched on that sample. Set timestamp to a free-running
150 MHz cycle counter (wrap modulo 2^64). `busy` covers acquisition AND DMA
drain; it clears only when the final IQ word handshakes. `done_toggle` then
copies the accepted ARM level. Poll equality to the requested ARM level AND
busy=0; inspect errors. Never rearm while busy. Config changes after ARM
do not affect that packet. A new valid ARM clears count, not sticky errors.

Only DEC=1 and 1<=LEN<=4096 are accepted; default LEN=4096. Other values
reject ARM, set error bit0, and emit no packet/no completion. Error bit1:
ARM while busy (ignored). Bit2: missing/out-of-order bin or wrong TLAST
during acquisition (capture aborted, no packet/no completion). Bit3 reserved.
Pulse `clear_errors` to clear sticky errors; a simultaneous fault wins.
An upstream ADC overflow/drop is not detectable from bin IDs: integration
must reject the capture if the existing upstream drop counters changed.

NCO removes positive residual frequency: multiply by exp(-j*phase);
phase starts zero and advances by unsigned FCW modulo 2^32 for each selected
sample. FCW = round(residual_hz / 480000 * 2^32) modulo 2^32. The DDS uses
the top 12 phase bits and signed18 Q1.16 sine/cosine tables (round-to-even);
full +1 is representable. Complex products sum in signed35; arithmetic >>16,
then saturate16. DEC=1 performs no filtering/extra decimation. This exact
amplitude convention is specified by the supplemental fixed golden model;
the earlier floating `nco_mix` is not a DDS amplitude reference.

SCAP output words: 0=0x53434150; 1=timestamp low; 2=timestamp high;
3=zero-extended channel; 4=FCW; 5=DEC (1); 6=LEN; 7=SRC; followed by
LEN IQ words `{Q,I}`. TLAST only on the final IQ word. For LEN=4096 allocate
16416 bytes and start S2MM before ARM; require exact received length and
successful status before accepting the capture. Timestamp marks the first
selected sample, not DMA delivery. No packet is emitted on invalid config.

## Suggested AXI GPIO map (main agent assigns actual base addresses)

Use dedicated dual-channel AXI GPIO instances, all GPIO outputs configured
as outputs and status inputs as inputs. These are GPIO offsets, not an
AXI-lite slave implemented by these cores. AXI GPIO channel1 DATA=0x00,
TRI=0x04; channel2 DATA=0x08, TRI=0x0c.

| GPIO instance | channel1 DATA | channel2 DATA |
|---|---|---|
| X5_CTRL | bit0 ARM toggle; bit1 clear_errors pulse; bits[7:4] CH; bits[11:8] DEC; bits[28:16] LEN | FCW[31:0] |
| X5_META | SRC[31:0] | optional reserved |
| X5_STATUS (inputs) | bit0 busy; bit1 done_toggle; bits[7:4] capture errors; bit8 PFB error; bits[28:16] captured_count | optional upstream drop snapshot |

`timestamp` should connect directly to a PL cycle counter, not two
independently updated CPU GPIO words. Main agent connects source fork, PFB,
capture, GPIO and replay DMA S2MM in the BD. Capture output is a single
32-bit AXIS packet, not a memory-mapped BRAM port. Validation results are
recorded separately; this interface document alone is not a PASS claim.

## Build inputs

Add both Verilog cores and the two initialization files to the integrated
project; set each HEX file's file type to `Memory Initialization Files` and
make it available in the simulation/synthesis working directory. The default
parameters are basenames `x5_pfb_coeff.hex` and `x5_nco_sine.hex`. Missing ROM
files are a build failure, not zero coefficients. A wiring-only optional top
is `src/rtl/nco_capture/x5_channel_capture.v`.

Initial generation uses `tools/x5_create_fft.tcl` after loading `tools/env.ps1`.
The shared XFFT is now FROZEN for v1d integration: do not regenerate it,
rebuild its output products, or rerun its project synthesis during integration.
The isolated XCI is
`build/work/x5_fft/x5_fft.srcs/sources_1/ip/pfb_fft16/pfb_fft16.xci`.
Import that XCI into the BD project; keep the instance/module name
`pfb_fft16`. This script refuses to overwrite an existing project. Generated
AMD files remain under ignored `build/work/`, not in third_party/vendor.
`tools/x5_run_sim.ps1 -Round 1` regenerates vectors from the existing AMD
bit-accurate C model and runs both benches. Use a background PowerShell
process with logs/X5* stdout/stderr redirection. `tools/x5_synth.tcl` runs a
XFFT OOC synthesis if missing, then full-core standalone place/route at 150 MHz;
it does not open the integrated BD or write a bitstream. All three OOC rounds
are complete; do not invoke this script again against the shared frozen IP.

## Verification and freeze evidence

Final RTL is frozen at the SHA256 values in `logs/X5_final_rtl_sources.log`.
`tools/x5_freeze_evidence.py` only reads inputs/reports and writes
`logs/X5_verification_final.json` and `logs/X5_sources_final.sha256`.
The JSON requires final round-3 NCO, PFB-chain, suite and OOC PASS markers
and unchanged RTL before reporting overall PASS. A missing completion marker
is `NOT_CONFIRMED`, not PASS. The SHA list includes all source files below
and a read-only snapshot of the shared XCI.

Final OOC round 3 completed: `logs/X5_synth_round3.stdout.log`,
`build/reports/x5_core/round3/routed_timing.rpt`, `routed_utilization.rpt`,
`routed_drc.rpt`. Routed at 150 MHz: WNS +0.296 ns, WHS +0.032 ns,
WPWS +2.203 ns, no failing endpoints; 2024 LUTs, 2971 FFs,
8 RAMB36 + 2 RAMB18, 12 DSPs. DRC has warnings, no errors or critical
warnings. PFB history mapped to LUTRAM despite the RTL block-RAM attribute;
capture storage and DDS tables use block RAM. Standalone constraints use
1 ns input/output delays and 0.10 ns clock uncertainty. The OOC clock has
no HD.CLK_SRC placement, so clock-skew estimation is limited. These results
do not establish integrated-BD timing or board acceptance.

Final round-3 standalone NCO passed 4513 exact words across lengths
4096/257/1/127 and FCWs 0x12345678/0xf1234567/0/0x20000000.
Coverage includes saturation, timestamp, header/KEEP/TLAST, config latching,
invalid config, busy rearm, sequence abort, reset and output backpressure.
Log: `logs/X5_nco_round3.log`.

Final round-3 PFB-chain simulation is running; no final-chain PASS is claimed
until `logs/X5_pfb_round3.log` and `logs/X5_sim_round3.stdout.log` contain
their completion markers. Expected coverage: 32769 paced inputs,
4097 frames / 65552 exact PFB IQ words, 4104 exact SCAP words (4096 IQ),
then reset/burst/backpressure and 2048 exact PFB IQ words. References use
the existing AMD bit-accurate FFT C model with `pfb_os2_fixed`, plus the
integer DDS supplement. Round 1 passed the same corpus on earlier RTL;
round 2 was explicitly superseded and stopped, not a final-chain PASS.

Source manifest (all paths relative to the repository root):

| Area | Files |
|---|---|
| PFB | `src/rtl/pfb/pfb_os2.v`, `src/rtl/pfb/x5_pfb_coeff.hex` |
| NCO/capture | `src/rtl/nco_capture/nco_capture.v`, `src/rtl/nco_capture/x5_nco_sine.hex`, `src/rtl/nco_capture/x5_channel_capture.v` |
| Golden supplement | `sim/golden/nco_capture_fixed.py` |
| Benches | `sim/tb/tb_x5_pfb.sv`, `sim/tb/tb_x5_nco_capture.sv` |
| Tools | `tools/x5_create_fft.tcl`, `tools/x5_vectors.py`, `tools/x5_run_sim.ps1`, `tools/x5_synth.tcl`, `tools/x5_freeze_evidence.py` |
| Contract/evidence index | `docs/x5_pl_interface.md` |
