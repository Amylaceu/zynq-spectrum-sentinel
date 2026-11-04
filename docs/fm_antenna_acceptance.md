# Antenna FM receive diagnostics — 2026-11-02

The user explicitly confirmed RX1A connected to an antenna, retaining J7/J8=2.5V and the original J22 LCD wiring. Antenna model was not specified further. AMC training remains paused.

## Wideband capture

The existing RF/LCD bitstream was reused without reconfiguration. The adapter disabled BIST/loopback, selected slow AGC and RX-only ENSM, tuned RX to98MHz and bandwidth24MHz. Eight guarded1MiB ADI DMA transfers completed at30.72MSPS. Native RX1/RX2 data were variable, all memory canaries remained intact, BBPLL and RX PLL lock bits were set, and both TX attenuations read89750mdB.

Readback LO97999998Hz is within2Hz of the requested nominal value; it is not an externally calibrated RF-frequency measurement. The spectrum shows candidates near90.0,95.8,100.9MHz and others. These are measured spectral peaks, not verified station identities or classifier outputs. `fm_scan_candidates.json` retains all detected candidates. Maximum raw-word clipping fraction was0.0005703 across both channels.

Evidence: `board/measurements/fm_scan_round1.json`, first native capture and averaged PSD NPZ; `report/figures/fm_band_antenna.png`.

## FM demodulation evidence

Narrow diagnostics use3.84MSPS,1.5MHz RF bandwidth and LO250kHz above each candidate. RX1 samples are stored as normalized ci16_le SigMF. Each capture is a separate DMA snapshot; gaps are explicitly recorded. No continuous-recording throughput claim is made.

- Candidate90MHz: capture passed, but four discriminator segments had only1.79–2.77dB pilot prominence and no stable19kHz evidence. It is not declared a verified FM broadcast.
- Candidate95.8MHz, first four snapshots: stable19kHz evidence in all four, pilot prominence18.58–19.69dB.
- Candidate95.8MHz, longer sixteen snapshots: all sixteen passed capture/canary checks and showed19kHz evidence, prominence16.14–27.21dB. LO readback96049998Hz,4,194,304×4=16,777,216 RX1 complex samples,4.3691s of captured IQ. Startup/edge trimming produces4.0333s of segmented playback.

Offline diagnostic processing on the Windows host: shift the candidate to baseband, polyphase decimate to480kHz,120kHz channel filter, phase-difference FM discriminator,50us deemphasis,50Hz–15kHz audio band and48kHz mono WAV. Each snapshot is independently processed and faded at its edges. Output amplitude is limited to0.3full scale. Synthetic tests verify known1kHz FM audio and19kHz pilot after offset tuning and reject noise-only pilot evidence. All20PS tests passed.

Measured19kHz stereo-pilot evidence strongly supports reception of an actual FM broadcast at the95.8MHz candidate. Station identity and intelligibility of speech/music are still pending user listening. This uses a deterministic FM diagnostic, not the paused neural classifier.

Outputs:

- `board/measurements/fm_audio_95800000_round2.json`: actual hardware capture/readback.
- `board/measurements/fm_95800000_round2_demod.json`: per-snapshot pilot evidence.
- `report/results/fm_95800000_round2_demod.wav`:4.03s playback for auditory confirmation.
- `report/figures/fm_95800000_round2_demod.png`: waveform and discriminator spectrum.
- Raw SigMF data remain locally under `data/captured/fm_diagnostic/` and on the board; large raw files are ignored by Git. Matching metadata and SHA512 are retained. `tools/analyze_fm_capture.py` validates raw hashes before processing.

The source adapter exposes receive tuning/gain/RSSI readback and RX-only operations. Reported chip RSSI is not an externally calibrated antenna power. After each diagnostic DMAC was disabled and hardware RF RESETB asserted; recorded GPIO=0, no in-flight buffer quarantine. No antenna TX operation or TX/RX cable was used.

## PYNQ allocation ownership correction

Inspection of the installed PYNQ2.7 XRT sources found that PynqBuffer.freebuffer acts through the cache/pointer ownership protocol. The project now supplies an explicit return target using that installed backend's release routine; no installed/vendor files were edited. This backend-specific adapter fails closed if the expected protocol is absent.

An initial immediate CmaFree check ran before deleting the NumPy array owner and reported failure. After owner deletion/GC and a short wait, three1MiB allocation/release cycles passed. The sixteen8MiB receive allocations subsequently reused the same physical address and completed with intact guards. Instantaneous CmaFree values are not interpreted as a fixed total allocation capacity or as proof of the earlier network outage's cause.

`sentinel/dma.py` now uses this owned allocator by default; diagnostic buffers release only after transfer completion. Timeout paths continue to retain ownership and keep the background process alive until explicit board reset.

## Remaining scope

LCD colorbars and animation are confirmed, but this captured RF spectrum is not yet streamed to the LCD. The processing above ran offline on the PC. Board headphone playback, sustained/gap-free recording, numerical timing-window measurement, TX-DMA bit-exact loopback and complete G2 acceptance remain open. The observed pilot is not used to mark those tests passed.

## User listening feedback and voice-focused preview

User confirmed hearing human speech in the original95.8MHz WAV, but reported particularly loud electric-like noise. Speech audibility is confirmed; acceptable audio quality is not. The user's record with the exact WAV hash is `board/measurements/fm_audio_listening_feedback.json`; earlier generated demodulation JSON represents the pre-feedback checkpoint.

The audio spectrum did not establish a50/100Hz mains-hum fault. Narrow peaks include musical-note-like frequencies, so no blanket mains/harmonic notch bank was applied and no power-supply/grounding diagnosis was made.

An independent `--profile voice` preview uses the same original IQ bytes: retains50us deemphasis, changes the audio passband to150–3400Hz, bridges only short abnormal discriminator slips (at most8samples at480kHz and capped at2% of a segment), and overlaps faded snapshot edges by5ms. Original wideband audio remains unchanged. This is a diagnostic voice profile and loses bass/music bandwidth; it is not a reconstruction of missing capture intervals.

Result `report/results/fm_95800000_round2_voice.wav` is3.9583s. Largest corrected short-slip fraction was0.0167946. Relative to300–3000Hz energy,0–120Hz energy decreased15.58dB and5–15kHz energy decreased29.62dB. These are spectral-band attenuation measurements, not clean-reference SNR improvements. File `board/measurements/fm_audio_voice_comparison.json` records both profiles.

A synthetic FM test verifies retention of a1kHz desired tone and rejection of8kHz content in the voice profile. All21PS tests passed. No new board program, RF capture, wiring or model training was needed. Subjective improvement of the new preview is pending user listening; G2/audio quality remains open.

## Actual antenna correction and digital-path check

The user reported the voice preview improved audio but noise remained loud. On clarification, RX1A was actually connected to a2.4GHz panel antenna during the current FM setup. That antenna's stated operating band differs substantially from95.8MHz; it is a plausible contributor to weak reception, not a proven exclusive cause of all noise. The replacement with the user's existing20–512MHz magnetic antenna is pending. Initial antenna-model-unspecified records are historical; `antenna_type_correction.json` records the subsequent explicit identification.

An independent internal RX PRBS check was run at both30.72MSPS and3.84MSPS. The implementation follows pinned no-OS PN9 selection and restores saved channel selection after the test; RX BIST only, TX muted. After20ms settling, PN_ERR/PN_OOS sticky bits were cleared, followed by500ms observation. All four channel status registers were0 at each rate; ADC status was0xD (valid bit set), clock-frequency registers80542 and10068 respectively, and the final reset GPIO was0. Evidence: `board/measurements/rx_prbs_rates.json`.

These finite sticky-flag checks observed no digital PN error/out-of-sync; they are not error counters, a continuous BER specification, a guarantee against intermittent faults, numerical timing-window qualification, or TX-DMA bit-exact loopback. The comparison of raw antenna audio will resume after the antenna change, rather than marking the current audio quality passed.

## Confirmed antenna replacement and repeat capture

The user confirmed replacement by the existing20–512MHz magnetic antenna, retaining J7/J8=2.5V and LCD wiring. The first capture stopped at the loaded-overlay check before RF/DMA. The reason for the unloaded state was not inferred. Reloading the same verified bitstream restored ten0x0A identity reads; no HDL or constraints changed. Logs: `logs/P5.3_fm_round3_precondition_failure.log`, `logs/P5.3_fm_round3_reload.log`.

The subsequent95.8MHz round3 passed sixteen8MiB guarded transfers at3.84MSPS, with the same LO readback96049998Hz,1.5MHz bandwidth and slow AGC. Both TX attenuations remained89750mdB; final GPIO0 and no in-flight buffers. SigMF SHA512 verification passed.

| Measurement | Earlier2.4GHz panel, round2 |20–512MHz magnetic, round3 |
|---|---:|---:|
|19kHz pilot prominence, median |17.58dB |30.80dB |
|Pilot evidence across snapshots |16/16 |16/16 |
|RX1 AGC gain, median |73dB |59dB |
|Chip RSSI readback, median, uncalibrated |-101125mdB |-79250mdB |
|Maximum raw-word clipping fraction |0.00078416 |0.00013876 |
|Voice-profile short-slip correction fraction, median |0.013608 |0.000715 |

These observations support improved reception with the corrected antenna setup. They do not measure clean-reference audio SNR or isolate antenna gain: broadcast content, measurement time and placement were not controlled. `tools/compare_fm_antennas.py` asserts matching bit/rate/LO/sample count, capture checks and final state, and writes `board/measurements/fm_antenna_comparison.json`.

New previews: `report/results/fm_95800000_round3_demod.wav` (4.03s) and `report/results/fm_95800000_round3_voice.wav` (3.96s). Both use gapped snapshots processed on the PC. Quality awaits user listening; full G2, live spectrum on LCD and board headphone output remain incomplete.

Subsequent user feedback: round3 audio clearly improved and retained only a small amount of noise. Exact file hash and feedback are recorded separately in `fm_audio_listening_feedback.json`; no clean-reference SNR or noise-free audio claim is made. A reported blank LCD was restored by reloading the same joint image, and the user confirmed colorbars/top animation again. The screen's earlier blank state is not attributed to a proven cause. Live RF spectrum and board headphone output are still incomplete.
