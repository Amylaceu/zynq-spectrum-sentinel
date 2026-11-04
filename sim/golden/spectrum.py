"""Integer spectrum reference. Numeric representation: docs/spectrum_numeric.md."""

import numpy as np
from scipy.signal.windows import blackmanharris, hann

from .fft_cmodel import fft_i16
from .params import FFT_OUT_BITS, IQ_BITS, WIN_BITS


def window_coefs(kind="bh4", n=2048, bits=18):
    if not isinstance(n, int) or n < 8 or not 2 <= bits <= 30:
        raise ValueError("Invalid window dimensions")
    windows = {"bh4": blackmanharris, "hann": hann}
    if kind == "rect":
        w = np.ones(n)
    elif kind in windows:
        w = windows[kind](n, sym=False)
    else:
        raise ValueError(f"Unknown window: {kind}")
    scale = 1 << (bits - 1)
    return np.clip(np.rint(w * scale), -scale, scale - 1).astype(np.int64)


def fft_fixed(x_int16, win):
    """Windowed forward FFT in natural order, returned as N x 2 signed Q1.23.

    IQ can be interleaved words or N x 2. Native scaled FFT is 16-bit;
    the 24-bit transport is LEFT aligned (eight zero low bits).
    """
    x = np.asarray(x_int16)
    w = np.asarray(win)
    if x.ndim == 1 and x.size % 2 == 0:
        x = x.reshape(-1, 2)
    if x.ndim != 2 or x.shape[1] != 2 or w.shape != (len(x),):
        raise ValueError("Expected N IQ pairs and N window coefficients")
    if not np.issubdtype(x.dtype, np.integer) or not np.issubdtype(w.dtype, np.integer):
        raise ValueError("IQ and window must contain integer words")
    if np.any(x < -32768) or np.any(x > 32767):
        raise ValueError("Input outside signed 16-bit range")
    if np.any(w < -(1 << (WIN_BITS - 1))) or np.any(w >= (1 << (WIN_BITS - 1))):
        raise ValueError("Window outside signed Q1.17 range")
    windowed = (x.astype(np.int64) * w.astype(np.int64)[:, None]) >> (WIN_BITS - 1)
    return (fft_i16(windowed) << (FFT_OUT_BITS - IQ_BITS)).astype(np.int32)


def power_u32(X):
    """48-bit Q2.46 I^2+Q^2; discard 16 low bits to form uint32 Q2.30."""
    x = np.asarray(X)
    if x.ndim < 1 or x.shape[-1] != 2 or not np.issubdtype(x.dtype, np.integer):
        raise ValueError("Expected integer complex pairs in the last dimension")
    if np.any(x < -(1 << 23)) or np.any(x >= (1 << 23)):
        raise ValueError("FFT word outside signed 24-bit range")
    x = x.astype(np.int64)
    return ((x[..., 0] ** 2 + x[..., 1] ** 2) >> 16).astype(np.uint32)


def welch_update(P, pw, shift=3):
    a, b = np.asarray(P), np.asarray(pw)
    if a.shape != b.shape or not isinstance(shift, int) or not 0 <= shift <= 31:
        raise ValueError("Mismatched powers or invalid shift")
    for v in (a, b):
        if not np.issubdtype(v.dtype, np.integer) or np.any(v < 0) or np.any(v > 0xFFFFFFFF):
            raise ValueError("Power outside uint32 range")
    a, b = a.astype(np.int64), b.astype(np.int64)
    return (a + ((b - a) >> shift)).astype(np.uint32)


DB_MANTISSA_LUT_Q16 = np.rint(10 * np.log10(1 + np.arange(256) / 256) * 65536).astype(np.int64)
DB_LOG2_Q16 = int(round(10 * np.log10(2) * 65536))


def to_db_q88(p_u32):
    """10*log10(integer power), Q8.8; zero maps to -128 dB sentinel.

    No floating logarithm is evaluated on data: leading-one + 8-bit LUT,
    Q16.16 accumulation and one final rounding. dBFS subtracts the Q2.30
    reference (10*log10(2^30)); this function returns raw power in dB.
    """
    p = np.asarray(p_u32)
    if not np.issubdtype(p.dtype, np.integer) or np.any(p < 0) or np.any(p > 0xFFFFFFFF):
        raise ValueError("Power outside uint32 range")
    flat = p.astype(np.uint64).reshape(-1)
    result = np.full(flat.shape, -32768, dtype=np.int16)
    active = flat != 0
    v = flat[active]
    exponent = np.zeros(v.shape, dtype=np.int64)
    remainder = v.copy()
    for shift in (16, 8, 4, 2, 1):
        choose = remainder >= (1 << shift)
        exponent[choose] += shift
        remainder[choose] >>= shift
    mantissa = np.empty_like(v)
    high = exponent >= 8
    mantissa[high] = v[high] >> (exponent[high] - 8).astype(np.uint64)
    mantissa[~high] = v[~high] << (8 - exponent[~high]).astype(np.uint64)
    index = (mantissa - 256).astype(np.int64)
    db_q16 = exponent * DB_LOG2_Q16 + DB_MANTISSA_LUT_Q16[index]
    result[active] = ((db_q16 + 128) >> 8).astype(np.int16)
    return result.reshape(p.shape)
