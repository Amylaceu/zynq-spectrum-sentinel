# RTL simulation acceptance

| Step/test | Status | Evidence | Scope |
|---|---|---|---|
| N2 FFT IP generation | PASS | logs/N2_fft_round1.log |2048/16/18/scaled/convergent/natural, non-realtime|
| N2 tb_spec_fft | PASS |spec_fft_compare.json|4 BH4 frames,16384 words, exact AMD C-model reference; randomized stalls|
| N2 tb_spec_stages | PASS |n2_component_acceptance.json|65536 words across window/power/Welch/dB, random stalls and numeric endpoints|
| N2 tb_spec_regs | PASS |n2_component_acceptance.json|AW/W skew, byte strobes, RO behavior, delayed held responses|
| N2 full spec_front simulation | PASS |spec_front_*_compare.json|4 frames; exact FFT/power/Welch/dB;2240 maxima; independent sinks and20000-cycle stall|
| N2 standalone modules150MHz | PASS |build/reports/modules/*_timing.rpt|window+1.914,power+3.460,Welch+0.934,dB+0.838ns OOC WNS|
| N2 display decimator | PASS |local tb_spec_reduce.log|signed maxima,decim2,1120 pixels from4 frames|
| N2 full top150MHz | PASS |n2_acceptance.json; build/reports/modules/spec_front_*|setup+0.135ns, internal hold+0.059ns;3725LUT/5463FF/14.5BRAM/25DSP; OOC virtual I/O hold deferred to N4|
| N2 IP packaging | PASS |logs/N2_package_round2.log|integrity and final150MHz/reset/all-bus metadata verified|

Detailed logs and scalar outputs remain local under logs/ and ignored sim/results files. Committed golden vectors, testbenches, output hashes and comparison JSON permit reproduction. See docs/n2_spec_front.md for commands and the two corrected infrastructure errors. These results do not establish an integrated hardware frequency spectrum monitor.

## N3 CFAR acceptance

| Test | Result | Scope |
|---|---|---|
|CA/GO/SO × interior/wrap-edge targets|PASS|6 primary cases, exact circular-window golden|
|Saturation/overflow/empty/equality/N1/N64/bridged peak|PASS|7 further cases,13 total|
|Complete output comparisons|PASS|threshold/hit/dB/occupancy26624 each; target words1664, zero discarded/mismatched|
|AXIS/AXI-Lite|PASS|independent random and long stalls, held payload, target list/IRQ, WSTRB, skewed AW/W, RO|
|Occupancy endpoint|PASS|0xFFFE→0xFFFF→saturate, non-hit and clear|
|Python driver|PASS|4 tests, sequence-race refusal, invalid data/config, coherent snapshots|
|150MHz routed implementation|PASS|WNS+0.280ns, internal hold+0.127ns;1897LUT/1230FF/15BRAM/2DSP|
|IP package|PASS|integrity, clock/reset and five associated buses|

Evidence: n3_acceptance.json, data/reference/cfar/n3/manifest.json, build/reports/modules/cfar_core_*.rpt. No N3 board download. OOC virtual I/O hold and full-system throughput remain N4 obligations.

## N4 input substep (not full N4 acceptance)

ADC tap/xpm_fifo_async simulation PASS:4096 normalized IQ words, two complete frames,61.44MHz/150MHz clocks, random stalls, overflow/mismatch flags and reset. sim/results/n4_adc_tap_acceptance.json. No sentinel_v1 system build or board download yet.

N4 source/LCD primitives PASS:16384 exact IQ words across8 cases;source150MHz WNS+0.198ns/internal hold+0.157ns. LCD initialization68 bus writes, dynamic pulse widths,83 region/scroll command-data words and invalid bounds tested. sim/results/n4_primitives_acceptance.json. Full N4 remains DOING; no sentinel_v1 download.

N4 LCD engine substep PASS:89600 spectrum and560 waterfall pixels exact; coherent snapshot banks/whole-frame drops; full-clear/UI/scroll command model; AXI integration;3 PS tests.50/150MHz routed WNS+1.900ns/internal hold+0.089ns,1493LUT/948FF/2BRAM/1DSP;68 safe CDC endpoints,0 unsafe/unknown. sim/results/n4_display_acceptance.json. Full N4 remains DOING; no board download or measured display-rate claim.

N4 perf/observers substeps PASS: handshake/atomic counter/marker tests;150MHz WNS+1.828ns/internal hold+0.142ns,265LUT/903FF/0BRAM/0DSP. Two complete power snapshots4096words and20 asynchronous IRQs pass;9 related PS tests pass. sim/results/n4_perf_acceptance.json. BD validation is separate and not yet passed.
