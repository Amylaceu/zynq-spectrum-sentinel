# N2 spec_front acceptance

Prerequisites: N1/G2 DONE (a7922e4); P2.2/P2.3/P2.8 reference files and numeric contract present. Runbook80 takes precedence over30: SSD1963/J22 display560 points, no RGB/VDMA. No board RF operation is needed for N2.

## Numeric contract and validated components

FFT is AMD XFFT9.1,2048-point pipelined streaming,16-bit native input/output,18-bit twiddles,scaled,convergent rounding,natural-order output. Scale schedule [2,2,2,2,2,1], config bits12:1=0x6AA and bit0=forward, hence16'h0D55. Confirmed against the locally generated AMD demo testbench and then against P2.8's four-frame bit-accurate reference. Non-realtime throttle supports required AXIS backpressure (80's mandatory stall test overrides30's realtime suggestion). Native16 output is shifted left8 only for24-bit transport. It does not gain precision.

spec_window: BH4/Hann/rect periodic2048 coefficient ROMs, signed18 Q1.17; multiply signed16x18, arithmetic truncate17. Coefficients exported from the existing golden model as HEX/COE. Selection latched at input frame start. Four-clock sample service, valid payload held under stall, expected2048-word TLAST check. At150MHz its unstalled bound is37.5MSPS; this is a design bound, not yet measured integrated throughput.

spec_power: native16 I/Q squares summed as unsigned32; equivalent to24-bit left-aligned squares right-shifted16. Elastic two-stage pipeline. Endpoint(-32768,-32768) yields0x80000000.

spec_welch:2048x32 BRAM history, logical zero state on first frame after reset without resetting RAM contents. The golden signed64 arithmetic is implemented with an exact signed33 difference (uint32 subtraction range is [-4294967295,4294967295], so higher bits are sign copies). A registered subtraction stage precedes the signed shift/add stage; falling values remain exact, per-frame shifts0..31 are supported. Four-clock sample service; regenerated numeric tests pass.

spec_db: leading-one plus8-bit mantissa LUT, Q16.16 exponent constant197283, one final+128 then shift8 rounding, uint32 zero -> signed16 0x8000. Four-clock service. No floating logarithm in RTL.

spec_ctrl.yaml and generated AXI-Lite bank: CTRL(EN,WIN_SEL),AVG_SHIFT(reset3),DISP_DECIM(reset1),RO FRAME_CNT,RO VERSION0x53500001. One outstanding write with independently latched AW/W, byte strobes, held B/R responses. YAML BaseLoader preserves key off rather than converting it to False.

## Commands and evidence

- tools/build_spec_fft.ps1: isolated generated IP project build/work/spec_front/spec_front.xpr; exit0, logs/N2_fft_round1.log. No regenerated third_party/vendor files.
- tools/test_spec_fft.ps1 -Attempt3: actual mixed-language XFFT simulation,4 BH4 frames,16384 scalar24-bit words exactly match exp_fft.hex; randomized output stalls and payload stability checked. sim/results/spec_fft_compare.json; logs/N2_fft_sim_round3.log.
- tools/test_spec_stages.ps1 -Attempt1:65536 words total, randomized backpressure; all3 window choices, native input endpoints, averaging shifts0/3/31 and decreasing uint32 history, logarithm zero/powers-of-two neighbors/full uint32 endpoints. PASS. sim/results/n2_component_acceptance.json; logs/N2_stages_round1.log.
- tools/test_spec_regs.ps1 -Attempt1: skewed AW/W both orders, WSTRB lane isolation, RO VERSION/FRAME_CNT, delayed B/R ready, held RO read snapshot despite changing counter. PASS, logs/N2_regs_round1.log.
- tools/synth_spec_stages.ps1 -Attempt1: 150MHz OOC synthesis/place/route accepted: window +1.914ns, power +3.460ns, pipelined Welch +0.934ns, dB +0.838ns. Reports build/reports/modules/*.rpt; DCPs remain local. These are standalone OOC core timings, not board-level interface margin.

First FFT simulation launch failed because shell redirection and the vendor tool both tried to own xvhdl.log. Console and tool logs are now separate. Second failed on missing timescale in RTL while SV had a timescale; xelab now sets a default1ns/1ps. Third fully passed without relaxing numeric comparison. Native vendor model/library remains local and ignored.

## Integrated RTL and current acceptance

Added spec_fftshift: two2048x32 banks, natural bin addresses XOR1024 on write, ordered readout with complete-frame ownership. Full banks stop writes until their last read handshake, avoiding overwrite under unbounded downstream stalls. Added axis_fork2: independent pending bits for PWR and dB consumers, ensuring one consumer cannot duplicate data while the other stalls. Added spec_display_reduce: pixel j takes signed Q8.8 maximum from bins floor(j*2048/560)..floor((j+1)*2048/560)-1. DISP_DECIM is a per-frame display decimator (0 treated as1), while PWR always emits all2048 bins. CTRL.EN gates a new input frame; an already accepted frame drains fully. Window/average/display parameters are latched at the respective module frame boundaries. Software must disable new input and drain before changing a multi-module configuration atomically.

spec_front instantiates all modules and the generated register bank. PWR output is fftshifted Welch power (uint32 Q2.30) with11-bit bin index and2048-word TLAST. Display output has560 signed16 Q8.8 raw integer-power dB values with10-bit pixel index and560-word TLAST. FRAME_CNT increments on complete PWR output frame acceptance. Debug tap valid pulses mark accepted FFT, shifted power and full2048-bin dB values for testbench comparisons; they are not separate backpressured consumers. error_sticky captures framing/FFT overflow events. N4 rendering must convert raw dB to dBFS with sufficiently wide signed arithmetic and handle the zero sentinel explicitly.

Integrated tb_spec_front round1 exposed a declaration-order error in the new top; fixed without changing arithmetic. Round2 passed4 complete frames: FFT16384 scalar words, shifted power8192,Welch8192,full dB8192,display2240. Separate PWR/display sinks use random ready patterns; PWR is also stopped20000 cycles to fill frame buffers and propagate input backpressure. Every scalar word, bin/pixel index,TLAST,held payload and final frame count is checked. All five complete-vector golden comparisons passed, with no dropped prefix/tolerance. Separate tb_spec_reduce passed signed extrema and decim2 over4 input frames (1120 expected pixels).

Synthesis corrections: first launcher placed tool options after -tclargs, causing a usage error before synthesis. Reordered options. Original Welch combined64-bit subtract/shift/add failed150MHz WNS=-1.800ns; pipelined exact33-bit arithmetic retained bitwise results. An initial modified Welch synthesis stopped with only Common17-69 after technology mapping; the original log is retained as logs/N2_spec_welch_synth_pipeline_first_failure.log. Isolated standalone modules from unrelated unfinished sources and moved the150MHz XDC ahead of synthesis; subsequent Welch/dB implementations passed. Do not attribute the opaque tool error to a proven hardware or arithmetic fault. The old failing timing report is retained under logs/N2_spec_welch_baseline_failed_timing.rpt, not mistaken for the current passing report.

## Final implementation and packaging

Full spec_front round2 synthesis/place/route passed at150MHz: setup WNS +0.135ns, internal register-to-register hold +0.059ns;3725 LUT,5463 FF,14.5 BRAM36 equivalents,25 DSP. FFTshift uses4 RAMB36 primitives. Its earlier two syntactic read sites prevented block-RAM inference and consumed10624 LUT; a single synchronous RAM read port with valid-controlled ownership restored BRAM inference. No RAM contents/output reset is required; invalid data never escapes. Full-chain simulation round3 after this change again matched all five golden vectors exactly.

OOC virtual I/O ports have no physical partition locations, and zero I/O delays produce negative virtual input hold paths. This acceptance covers core setup and internal hold only; it does NOT establish full-system I/O hold closure, integrated throughput, or board operation. N4 must verify the real clocks/interfaces and all setup/hold paths. No false-path relaxation was used to hide these paths.

IP package round2 passed ipx::check_integrity. Final component metadata declares150000000Hz, active-low aresetn, and all four associated AXI/AXIS interfaces. The local generated package is build/work/packaged_ip_round2/spec_front; only project-owned RTL/scripts and reproducible artifacts are committed. Import-time provisional clock/description warnings were resolved before final integrity checking; missing Product Guide remains cosmetic.

Run `.venv/Scripts/python tools/accept_n2.py` to check exit markers, complete comparison counts, reports, IP metadata, and capture SHA256 provenance in sim/results/n2_acceptance.json. Detailed local logs: logs/N2_front_round3.log, logs/N2_front_synth_round2.log, logs/N2_package_round2.log. N2 DONE; N3 follows. M-A remains incomplete until N3–N5 pass.
