"""Causal 2x oversampled analysis PFB, with explicit phase/word conventions."""

import numpy as np
from scipy.signal import firwin, kaiser_beta, upfirdn

from .fft_cmodel import fft_integer


def design_prototype(m=16, taps_per_phase=8, atten_db=70, bits=18):
    if m < 4 or m & (m - 1) or taps_per_phase < 2 or not 8 <= bits <= 30:
        raise ValueError("Invalid prototype dimensions")
    if atten_db <= 0:
        raise ValueError("Invalid Kaiser attenuation")
    h = firwin(m * taps_per_phase, 1 / m, window=("kaiser", kaiser_beta(atten_db)))
    scale = 1 << (bits - 1)
    return np.clip(np.rint(h * scale), -scale, scale - 1).astype(np.int64)


def _validate(m, d, h):
    if not isinstance(m, int) or m < 8 or m & (m - 1) or d * 2 != m:
        raise ValueError("Expected power-of-two M>=8 and D=M/2")
    if np.asarray(h).ndim != 1 or len(h) % m:
        raise ValueError("Prototype must have a whole number of phases")


def _phase_sums(x, h, m, d):
    # Frame n has endpoint t=n*D; history before sample 0 is zero.
    t = np.arange(0, len(x), d)
    offsets = np.arange(len(h))
    indices = t[:, None] - offsets
    padded = np.r_[np.zeros(len(h), dtype=x.dtype), x]
    history = padded[indices + len(h)]
    return (history * h).reshape(len(t), -1, m).sum(axis=1)


def _commute_and_rotate(phases, m, d):
    # Reverse phase indices so positive input frequencies map to positive bins.
    # Rolling the FFT input cancels exp(+j*2*pi*k*nD/M) at channel center.
    q = phases[:, (-np.arange(m)) % m]
    rotation = (np.arange(len(q)) * d) % m
    return np.take_along_axis(q, (np.arange(m)[None, :] - rotation[:, None]) % m, axis=1)


def pfb_os2(x, h, m=16, d=8):
    _validate(m, d, h)
    x = np.asarray(x, dtype=np.complex128)
    if x.ndim != 1:
        raise ValueError("Expected one-dimensional complex IQ")
    if len(x) == 0:
        return np.empty((0, m), dtype=np.complex128)
    h = np.asarray(h)
    hf = h.astype(np.float64) / (1 << 17) if np.issubdtype(h.dtype, np.integer) else h
    return np.fft.fft(_commute_and_rotate(_phase_sums(x, hf, m, d), m, d), axis=1)


def pfb_os2_fixed(x_int16, h_int, m=16, d=8):
    """Return [frames,M,2] int16, normalized to the input IQ integer scale.

    16x18 MAC with 40-bit accumulator; arithmetic >>9 retains eight fractional
    bits before a 24-bit scaled AMD FFT. Restore FFT /M and discard eight
    fractional bits once, then saturate16. See docs/pfb_numeric.md.
    """
    _validate(m, d, h_int)
    x, h = np.asarray(x_int16), np.asarray(h_int)
    if x.ndim == 1 and x.size % 2 == 0:
        x = x.reshape(-1, 2)
    if x.ndim != 2 or x.shape[1] != 2 or not np.issubdtype(x.dtype, np.integer):
        raise ValueError("Expected integer IQ pairs")
    if not np.issubdtype(h.dtype, np.integer) or np.any(h < -131072) or np.any(h > 131071):
        raise ValueError("Expected signed 18-bit Q1.17 prototype")
    if np.any(x < -32768) or np.any(x > 32767):
        raise ValueError("IQ outside signed 16-bit range")
    result = np.empty(((len(x) + d - 1) // d, m, 2), dtype=np.int16)
    if not len(x):
        return result
    lanes = []
    for lane in (0, 1):
        acc = _phase_sums(x[:, lane].astype(np.int64), h.astype(np.int64), m, d)
        if np.any(acc < -(1 << 39)) or np.any(acc >= 1 << 39):
            raise OverflowError("40-bit PFB MAC overflow")
        lanes.append(_commute_and_rotate(acc >> 9, m, d))
    fft_input = np.stack(lanes, axis=-1)
    for frame in range(len(result)):
        native = fft_integer(fft_input[frame], width=24)
        restored = (native * m) >> 8
        result[frame] = np.clip(restored, -32768, 32767).astype(np.int16)
    return result


def channel_center(ch, fs, m=16):
    if not isinstance(ch, (int, np.integer)) or not 0 <= ch < m or fs <= 0:
        raise ValueError("Invalid channel or sample rate")
    return (ch if ch < m // 2 else ch - m) * fs / m


def select_channel(f_hz, fs, m=16):
    if fs <= 0 or not -fs / 2 <= f_hz < fs / 2:
        raise ValueError("Frequency must lie in [-fs/2,fs/2)")
    spacing = fs / m
    # Nearest center, deterministic tie towards the greater signed frequency.
    signed_bin = int(np.floor(f_hz / spacing + 0.5))
    return signed_bin % m, f_hz - signed_bin * spacing


def nco_mix(y, f_res, fs_ch, phase_bits=32):
    """Remove residual frequency with a quantized phase increment (start phase 0).

    This is a phase-quantized reference; DDS amplitude bit matching is P3 work.
    """
    if fs_ch <= 0 or not 8 <= phase_bits <= 32 or abs(f_res) >= fs_ch / 2:
        raise ValueError("Invalid NCO parameters")
    y = np.asarray(y)
    if y.ndim != 1:
        raise ValueError("Expected one channel")
    modulus = 1 << phase_bits
    fcw = int(np.rint(f_res / fs_ch * modulus)) % modulus
    phase = (np.arange(len(y), dtype=np.uint64) * fcw) & (modulus - 1)
    return y * np.exp(-2j * np.pi * phase.astype(np.float64) / modulus)


def decimate(y, r):
    """Causal cascade of 63-tap Kaiser half-band filters; no hidden delay trim."""
    if not isinstance(r, int) or r not in (1, 2, 4, 8):
        raise ValueError("Decimation must be 1,2,4,8")
    out = np.asarray(y)
    if out.ndim != 1:
        raise ValueError("Expected one channel")
    if len(out) == 0:
        return out.copy()
    halfband = firwin(63, 0.5, window=("kaiser", 8.6))
    stages = r.bit_length() - 1
    for _ in range(stages):
        count = (len(out) + 1) // 2
        out = upfirdn(halfband, out, down=2)[:count]
    return out
