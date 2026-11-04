# X2 streaming architecture and acceptance boundaries

This is an independent `sentinel_v1c` implementation. Accepted v1/v1b sources,
artifacts and their manifests remain unchanged. X1 remains **FAIL** on its
95.8 MHz detection-rate metric; throughput work does not alter that result.

## Datapath

`AD9361 -> adc_tap_x2 async FIFO -> src_mux -> spec_front_x2 -> frame_queue_x2`

The 150 MHz front end retains the accepted window, XFFT, power and FFTshift
arithmetic. Welch is a globally stalled three-stage pipeline with synchronous
history RAM. Its first frame uses zero history and the original right-shift
semantics. `AVG_SHIFT` is latched at bin zero. Both AXIS consumers use a
same-cycle-consume/refill broadcast. The original logarithm branch is drained.

Two full 2048-bin banks queue detector input. At each input frame's bin zero,
bank ownership determines whether to store or discard **the entire frame**.
The decision does not change if a bank becomes free midway through a frame.
The input is always ready outside reset. This decouples ADC sample loss from
intentional detector frame decimation; it does not claim CFAR processes every
FFT frame. Frame counters saturate at 0xffffffff.

After the queue, a broadcast feeds the detector and a logarithm/display branch.
Both use the same retained frames in the same order. LCD threshold and spectrum
sequence numbers therefore remain aligned despite queue frame drops. CFAR
register offsets/arithmetic stay compatible with X1. Configuration is latched
when the detector accepts a retained frame's first bin; it is not a timestamp
of original RF acquisition. Change configuration only with the source stopped.

## Counters and clock crossing

`adc_tap_x2.SAMPLE_DROP` counts valid I/Q pairs which cannot enter the FIFO
because it is full or reset-busy, excluding cycles during asserted FIFO reset.
I/Q-valid disagreement is a separate sticky error. The counter saturates and
resets with the ADC FIFO. Registered Gray encoding crosses two marked stages
to DSP; source-Q to first-D is constrained by max delay and bus skew (8 ns).
Only original single-bit status and asynchronous reset endpoints are excepted.
No blanket false path covers the counter bus.

`stream_stats_x2` at `0x43c80000` publishes an atomic token/ack snapshot:

| Offset | Field |
|---|---|
| 0x00 | SNAP_TOKEN (RW) |
| 0x04 | SNAP_ACK |
| 0x08 | SAMPLE_DROP |
| 0x0c | FRAME_DROP |
| 0x10 | FRAMES_IN |
| 0x14 | FRAMES_OUT (delivered to detector input) |
| 0x18 | status bits: overflow, valid mismatch, queue/display framing |
| 0x1c | FIFO_LEVEL |
| 0xfc | VERSION = 0x58320001 |

Each rate test reloads the image and initializes RF before recording its
initial snapshot. Only absolute sample-drop counters and sticky flags are used
for acceptance; any initial error also fails. Reset, saturation or a decreasing counter invalidates a run;
do not silently subtract away an error. At drain, FRAMES_IN = FRAMES_OUT +
FRAME_DROP; during acquisition up to two retained frames may still be pending.

## Evidence gates

1. Welch: exact signed arithmetic including full-range powers, frame-latched
   shifts (0/3/5/31), random stalls, output stability, continuous 8192 samples.
2. Queue: always-ready input, prolonged/random stalls, frame order and content,
   freeing a bank midway through a discarded frame, counter conservation.
3. ADC: actual XPM async FIFO, normalization, reset, deliberate overflow and
   input = drained + lost conservation, I/Q mismatch.
4. Full chain: actual non-backpressurable 30.72 MSPS ADC, 64 frames, zero lost
   samples, first 8192 powers exact, retained LCD spectrum/threshold pairing.
5. Routed full-system setup/hold/pulse/CDC/Gray skew, hashes and HWH map.
6. Original plan: four 600-second RX-only rate tests. User-requested fast path:
   four ascending 60-second screens, then one 600-second sustained test at the
   highest passing rate. Lower-rate screens are reported as `SCREENING_ONLY`,
   never as full sustained acceptance. All sample-loss, RSSI and consistency
   checks still apply. No RF bandwidth or display-fps result is inferred from a
   module simulation. Digital +/-Fs/2 is a frequency coordinate; the configured
   analog RF bandwidth is not claimed to be a measured flat band.

The measured throughput budget and highest zero-loss rate are filled in after
simulation and board tests, not from the plan's nominal performance estimates.
