"""Phase-quantized FM, envelope AM, and an offline 48 kHz resampling reference."""

from fractions import Fraction

import numpy as np
from scipy.signal import resample_poly


def _iq(y):
    y = np.asarray(y, dtype=np.complex128)
    if y.ndim != 1 or not np.all(np.isfinite(y)):
        raise ValueError("Expected finite one-dimensional complex IQ")
    return y


def fm_demod(y):
    """Radians/sample, phase quantized to signed16 where pi is 32768.

    Difference wraps modulo 2pi. First output is zero; it has no predecessor.
    CORDIC magnitude/zero handling must match this convention during RTL work.
    """
    y = _iq(y)
    phase = np.rint(np.angle(y) * (32768 / np.pi)).astype(np.int64)
    if not len(phase):
        return np.empty(0)
    delta = ((np.diff(phase) + 32768) & 65535) - 32768
    return np.r_[0, delta * (np.pi / 32768)]


def am_demod(y):
    """Envelope with causal integer DC estimate: dc += (amp-dc) >> 10.

    Magnitude uses unsigned16 Q1.15 (range 0..almost2); dc state starts at 0.
    Output is in normalized input amplitude units. No hidden startup trimming.
    """
    y = _iq(y)
    amplitude = np.clip(np.rint(np.abs(y) * 32768), 0, 65535).astype(np.int64)
    result = np.empty(len(y), dtype=np.float64)
    dc = 0
    for i, amp in enumerate(amplitude):
        dc += (int(amp) - dc) >> 10
        result[i] = (int(amp) - dc) / 32768
    return result


def resample_to_48k(a, fs_in):
    x = np.asarray(a)
    if x.ndim != 1 or fs_in <= 0 or not np.isfinite(fs_in):
        raise ValueError("Invalid audio input/sample rate")
    if not len(x):
        return x.copy()
    ratio = Fraction(48000 / fs_in).limit_denominator(1000000)
    if abs(float(ratio) * fs_in - 48000) > 1e-6:
        raise ValueError("Sample rate cannot be represented within the rational ratio limit")
    return resample_poly(x, ratio.numerator, ratio.denominator, window=("kaiser", 8.6))
