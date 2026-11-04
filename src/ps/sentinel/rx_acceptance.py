"""Acceptance of RX-injected AD9361 BIST tone in native I1,Q1,I2,Q2 order."""
import numpy as np


def analyze_bist_tone(words, sample_rate_hz):
    words = np.asarray(words)
    if words.dtype != np.dtype('<i2') or words.ndim != 2 or words.shape[1] != 4 or words.shape[0] < 1024:
        raise ValueError('Expected at least1024 native signed16 four-channel samples')
    if sample_rate_hz <= 0:
        raise ValueError('Positive sample rate required')
    channels = []
    n = words.shape[0]
    for channel in range(2):
        iq = words[:, 2*channel].astype(np.float64) + 1j*words[:, 2*channel+1].astype(np.float64)
        power = np.abs(np.fft.fft(iq))**2
        peak = int(power.argmax())
        peak_hz = float(np.fft.fftfreq(n, 1./sample_rate_hz)[peak])
        total = float(power.sum())
        fraction = float(power[peak]/total) if total else 0.
        item = dict(channel=channel+1, peak_hz=peak_hz,
                    peak_power_fraction=fraction,
                    rms=float(np.sqrt(np.mean(np.abs(iq)**2))),
                    minimum=int(words[:, 2*channel:2*channel+2].min()),
                    maximum=int(words[:, 2*channel:2*channel+2].max()))
        item['passed'] = bool(total > 0 and fraction > .95 and
                              abs(abs(peak_hz)-sample_rate_hz/32) <= sample_rate_hz/n and
                              item['minimum'] >= -2048 and item['maximum'] <= 2047)
        channels.append(item)
    return dict(expected_abs_tone_hz=sample_rate_hz/32,
                native_order=['i1','q1','i2','q2'], channels=channels,
                passed=all(c['passed'] for c in channels))
