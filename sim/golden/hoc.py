"""Even-order complex cumulants for approximately zero-mean symmetric IQ."""

import math

import numpy as np


MOMENTS = ((2, 0), (2, 1), (4, 0), (4, 1), (4, 2), (6, 0), (6, 1), (6, 2), (6, 3))


def _multiply(a, b):
    return (a[0] * b[0] - a[1] * b[1], a[0] * b[1] + a[1] * b[0])


def _signed48(value):
    return ((value + (1 << 47)) & ((1 << 48) - 1)) - (1 << 47)


def moments_fixed(x_int16, norm_shift):
    """Return nine raw complex signed-48 accumulators, count and scale metadata.

    Input arithmetic >>norm_shift; exact integer products; accumulator wraps at
    48 bits like ap_int<48>. `overflow` reports any prefix exceeding that range.
    Real moments M21/M42/M63 are represented as (integer,0), like other moments.
    """
    x = np.asarray(x_int16)
    if x.ndim == 1 and x.size % 2 == 0:
        x = x.reshape(-1, 2)
    if x.ndim != 2 or x.shape[1] != 2 or not np.issubdtype(x.dtype, np.integer) or len(x) == 0:
        raise ValueError("Expected nonempty integer IQ pairs")
    if np.any(x < -32768) or np.any(x > 32767) or not isinstance(norm_shift, int) or not 0 <= norm_shift <= 15:
        raise ValueError("Invalid IQ or normalization shift")
    sums = {f"M{p}{q}": (0, 0) for p, q in MOMENTS}
    overflow = False
    shifted = x.astype(np.int64) >> norm_shift
    peak = int(np.max(np.abs(shifted)))
    # Exact vector path whenever every intermediate/prefix is bounded in int64.
    # Keep Python integers for deliberately extreme configurations.
    if len(x) * max((2 * peak * peak)**3, 1) < 1 << 62:
        z = (shifted[:, 0], shifted[:, 1])
        zp = [(np.ones(len(x), dtype=np.int64), np.zeros(len(x), dtype=np.int64))]
        cp = [zp[0]]
        for _ in range(6):
            zp.append(_multiply(zp[-1], z))
            cp.append(_multiply(cp[-1], (z[0], -z[1])))
        for p, q in MOMENTS:
            value = _multiply(zp[p - q], cp[q])
            prefixes = [np.cumsum(lane, dtype=np.int64) for lane in value]
            overflow |= any(np.any(lane < -(1 << 47)) or np.any(lane >= 1 << 47) for lane in prefixes)
            sums[f"M{p}{q}"] = tuple(_signed48(int(lane[-1])) for lane in prefixes)
        return dict(sums, count=len(x), norm_shift=norm_shift, overflow=bool(overflow))
    for i, q in shifted:
        z = (int(i), int(q))
        conjugate = (z[0], -z[1])
        zp, cp = [(1, 0)], [(1, 0)]
        for _ in range(6):
            zp.append(_multiply(zp[-1], z))
            cp.append(_multiply(cp[-1], conjugate))
        for p, q in MOMENTS:
            name = f"M{p}{q}"
            re, im = _multiply(zp[p - q], cp[q])
            re += sums[name][0]
            im += sums[name][1]
            overflow |= not (-(1 << 47) <= re < 1 << 47 and -(1 << 47) <= im < 1 << 47)
            sums[name] = (_signed48(re), _signed48(im))
    return dict(sums, count=len(x), norm_shift=norm_shift, overflow=bool(overflow))


def _normalized(m):
    if "count" not in m:
        return m
    if m.get("overflow", False):
        raise OverflowError("HOC accumulator wrapped: increase norm_shift")
    scale = 2.0 ** (15 - m["norm_shift"])
    return {f"M{p}{q}": complex(*m[f"M{p}{q}"]) / m["count"] / scale**p for p, q in MOMENTS}


def cumulants(m):
    """Even-cumulant formulas with zero first/odd moments assumed.

    These nine even moments cannot estimate nonzero third-order terms. The
    approximation is explicit; IQ should have DC removed upstream. This helper
    never silently treats wrapped hardware accumulators as physical moments.
    """
    m = _normalized(m)
    a, b = m["M20"], float(np.real(m["M21"]))
    d, e, f = m["M40"], m["M41"], m["M42"]
    return {
        "C20": a,
        "C21": b,
        "C40": d - 3 * a**2,
        "C41": e - 3 * a * b,
        "C42": f - abs(a)**2 - 2 * b**2,
        "C60": m["M60"] - 15 * d * a + 30 * a**3,
        "C61": m["M61"] - 5 * d * b - 10 * e * a + 30 * a**2 * b,
        "C62": m["M62"] - 6 * f * a - 8 * e * b - d * np.conj(a)
                  + 6 * a**2 * np.conj(a) + 24 * a * b**2,
        "C63": m["M63"] - 9 * f * b - 3 * e * np.conj(a) - 3 * np.conj(e) * a
                  + 12 * b**3 + 18 * abs(a)**2 * b,
    }


def features_from_moments(m):
    c = cumulants(m)
    power = c["C21"]
    if not np.isfinite(power) or power <= 1e-20:
        return np.zeros(8, dtype=np.float32)
    names = ("C20", "C40", "C41", "C42", "C60", "C61", "C63", "C62")
    orders = (1, 2, 2, 2, 3, 3, 3, 3)
    return np.array([abs(c[name]) / power**order for name, order in zip(names, orders)], dtype=np.float32)


def hoc_features(x):
    """Eight scale/phase-invariant features; caller provides DC-removed IQ."""
    x = np.asarray(x, dtype=np.complex128)
    if x.ndim != 1 or not len(x) or not np.all(np.isfinite(x)):
        raise ValueError("Expected finite nonempty complex IQ")
    m = {f"M{p}{q}": np.mean(x ** (p - q) * x.conj() ** q) for p, q in MOMENTS}
    return features_from_moments(m)


def recommended_norm_shift(sample_count, peak=32768):
    """Conservative bound for 6th powers of complex IQ and signed48 sums."""
    if sample_count < 1 or not 0 <= peak <= 32768:
        raise ValueError("Invalid capture bound")
    for shift in range(16):
        bound = math.ceil(peak / (1 << shift))
        if sample_count * (2 * bound * bound)**3 < 1 << 47:
            return shift
    raise ValueError("Capture too long for this accumulator contract")
