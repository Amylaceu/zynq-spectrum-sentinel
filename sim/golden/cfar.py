"""Integer CA/GO/SO CFAR and deterministic left-to-right target clustering."""

from functools import lru_cache

import numpy as np
from scipy.optimize import brentq


TARGET_DTYPE = np.dtype([
    ("start", "<u2"), ("stop", "<u2"), ("peak_bin", "<u2"), ("flags", "<u2"),
    ("peak_pwr", "<u4"), ("sum_pwr", "<u4"),
])
U32_MAX = (1 << 32) - 1


def _power(p):
    x = np.asarray(p)
    if x.ndim != 1 or not np.issubdtype(x.dtype, np.integer):
        raise ValueError("Expected one-dimensional integer power")
    if np.any(x < 0) or np.any(x > U32_MAX):
        raise ValueError("Power outside uint32 range")
    return x.astype(np.uint64)


def cfar(p, mode="CA", n=16, g=2, alpha_q88=1974, dc_mask=3, edge="wrap"):
    """Return uint32 threshold and uint8 hits; p must already be fftshifted.

    The two reference sums and their combined sum must fit the RTL's 40 bits.
    Edge handling is circular only; unsupported alternatives are never guessed.
    """
    x = _power(p)
    mode = str(mode).upper()
    if mode not in ("CA", "GO", "SO") or edge != "wrap":
        raise ValueError("Expected CA/GO/SO with wrap edges")
    if not isinstance(n, int) or n < 1 or n & (n - 1) or 2 * n * U32_MAX >= 1 << 40:
        raise ValueError("Reference length must be a power of two fitting 40-bit sums")
    if not isinstance(g, int) or g < 0 or len(x) < 2 * (n + g) + 1:
        raise ValueError("Spectrum too short or invalid guard length")
    if not isinstance(alpha_q88, (int, np.integer)) or not 0 <= alpha_q88 <= 65535:
        raise ValueError("alpha must be unsigned Q8.8")
    if not isinstance(dc_mask, int) or dc_mask < -1:
        raise ValueError("dc_mask=-1 disables masking; otherwise use a nonnegative width")
    left, right = np.zeros_like(x), np.zeros_like(x)
    for offset in range(g + 1, g + n + 1):
        left += np.roll(x, offset)
        right += np.roll(x, -offset)
    shift = n.bit_length() - 1
    if mode == "CA":
        noise = (left + right) >> (shift + 1)
    elif mode == "GO":
        noise = np.maximum(left, right) >> shift
    else:
        noise = np.minimum(left, right) >> shift
    threshold = np.minimum((noise * int(alpha_q88)) >> 8, U32_MAX).astype(np.uint32)
    hit = (x > threshold).astype(np.uint8)
    if dc_mask >= 0:
        center = len(x) // 2
        hit[max(0, center - dc_mask):min(len(x), center + dc_mask + 1)] = 0
    return threshold, hit


@lru_cache(maxsize=64)
def alpha_for_pfa(pfa, n=16, mode="CA"):
    """Q8.8 multiplier for iid exponential power, with reproducible GO/SO MC.

    Gamma-distributed reference sums are sampled; analytically integrating the
    independent exponential CUT gives mean(exp(-alpha*Z)), reducing MC variance.
    This is a noise-model calibration, not a Pfa guarantee under correlated Welch.
    """
    mode = str(mode).upper()
    if not 0 < pfa < 1 or not isinstance(n, int) or n < 1 or n & (n - 1):
        raise ValueError("Invalid Pfa or reference length")
    if mode == "CA":
        alpha = 2 * n * np.expm1(-np.log(pfa) / (2 * n))
    elif mode in ("GO", "SO"):
        rng = np.random.default_rng(0xCF_A0 + n)
        a, b = rng.gamma(n, 1 / n, (2, 500000))
        z = np.maximum(a, b) if mode == "GO" else np.minimum(a, b)
        alpha = brentq(lambda value: np.mean(np.exp(-value * z)) - pfa, 0, 256)
    else:
        raise ValueError("Unknown CFAR mode")
    word = int(round(alpha * 256))
    if not 0 <= word <= 65535:
        raise ValueError("Requested Pfa needs an alpha outside unsigned Q8.8")
    return word


def cluster(hit, p, gap=2, max_targets=32):
    """Inclusive intervals; ties choose first peak; gap power is included in sum.

    Sum saturates to uint32. If excess intervals are dropped, bit0 is set on ALL
    retained records, so any consumer can see that this frame overflowed.
    """
    x = _power(p)
    h = np.asarray(hit)
    if h.shape != x.shape or np.any((h != 0) & (h != 1)) or len(x) > 65536:
        raise ValueError("Hit/power dimensions or bin values invalid")
    if not isinstance(gap, int) or gap < 0 or not isinstance(max_targets, int) or max_targets < 1:
        raise ValueError("Invalid clustering limits")
    indices = np.flatnonzero(h)
    if not len(indices):
        return np.empty(0, dtype=TARGET_DTYPE)
    groups = np.split(indices, np.flatnonzero(np.diff(indices) > gap + 1) + 1)
    output = np.zeros(min(len(groups), max_targets), dtype=TARGET_DTYPE)
    overflow = int(len(groups) > max_targets)
    for i, group in enumerate(groups[:max_targets]):
        start, stop = int(group[0]), int(group[-1])
        segment = x[start:stop + 1]
        peak = start + int(np.argmax(segment))
        output[i] = (start, stop, peak, overflow, int(x[peak]), min(int(segment.sum()), U32_MAX))
    return output


def pack_targets(t):
    x = np.asarray(t)
    if x.dtype != TARGET_DTYPE or x.ndim != 1:
        raise ValueError("Expected target records returned by cluster")
    return x.tobytes(order="C")
