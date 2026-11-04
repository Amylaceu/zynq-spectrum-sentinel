"""Offline F4 snapshot processing; no radio, DMA or PL configuration on import.

Power is relative to complex ADC full scale, not calibrated RF power. Tiles
from different antennas/AGC settings must remain separate panoramas.
"""
import math

import numpy as np


SAMPLE_RATE_HZ = 30720000
USABLE_HZ = 20000000
DC_GUARD_HZ = 150000
GROUPS = {'A': (70000000, 512000000), 'D': (512000000, 2700000000)}


def tile_centers(group, step_hz=8000000):
    """20 MHz tiles overlap by 12 MHz to cover masked LO/DC regions.

    The first/last centers are inset by 5 MHz, so the band boundaries also
    have valid samples away from the LO. This is a receive-only plan.
    """
    if group not in GROUPS:
        raise ValueError('F4 antenna group must be A or D')
    if type(step_hz) is not int or not 1000000 <= step_hz <= 9000000:
        raise ValueError('Step must be 1..9 MHz to cover masked DC with neighbours')
    low, high = GROUPS[group]
    first, last = low + USABLE_HZ // 4, high - USABLE_HZ // 4
    centers = list(range(first, last + 1, step_hz))
    if centers[-1] != last:
        centers.append(last)
    return centers


def welch_psd(iq, rate_hz=SAMPLE_RATE_HZ, nfft=4096, full_scale=2048.0,
              batch_segments=16):
    """Two-sided Hann/50%-overlap PSD, units FS^2/Hz, fftshift order.

    Input is complex signed ADC counts. Do not pass normalized floats with
    full_scale=2048. DC is retained here; stitching masks it explicitly.
    Sum(PSD)*bin_width equals window-weighted complex mean-square/full_scale^2.
    """
    iq = np.asarray(iq)
    if (iq.ndim != 1 or not np.iscomplexobj(iq) or not np.all(np.isfinite(iq))
            or type(nfft) is not int or nfft < 16 or nfft % 2 or len(iq) < nfft):
        raise ValueError('Need finite complex IQ and an even FFT length >=16')
    if not math.isfinite(rate_hz) or rate_hz <= USABLE_HZ:
        raise ValueError('Sample rate must exceed the usable tile width')
    if not math.isfinite(full_scale) or full_scale <= 0:
        raise ValueError('Positive full-scale reference required')
    if type(batch_segments) is not int or not 1 <= batch_segments <= 32:
        raise ValueError('Bound FFT working set to 1..32 segments')
    window = np.hanning(nfft)
    total = np.zeros(nfft, dtype=np.float64)
    segments = 0
    offsets = range(0, len(iq) - nfft + 1, nfft // 2)
    for start in range(0, len(offsets), batch_segments):
        batch = np.stack([iq[offset:offset+nfft] for offset in
                          offsets[start:start+batch_segments]])
        spectrum = np.fft.fft(batch / full_scale * window, axis=1)
        total += np.sum(np.abs(spectrum) ** 2, axis=0)
        segments += len(batch)
    total /= segments * rate_hz * np.sum(window ** 2)
    frequency = np.fft.fftshift(np.fft.fftfreq(nfft, 1.0 / rate_hz))
    return frequency, np.fft.fftshift(total)


def stitch(tiles, group, bin_hz=10000):
    """Average overlapping tile PSDs in linear power; leave gaps as NaN.

    Each tile supplies (actual_LO_hz, baseband_frequency_hz, linear_PSD).
    No interpolation is allowed to fill the masked DC/edge regions.
    Count=0 means unobserved, never a measured low-noise bin. ADC full-scale
    units do not compensate antenna response, receiver gain or RF filtering.
    """
    if group not in GROUPS or type(bin_hz) is not int or bin_hz <= 0:
        raise ValueError('Invalid antenna group or output bin width')
    low, high = GROUPS[group]
    frequency = np.arange(low + bin_hz / 2, high, bin_hz, dtype=np.float64)
    total = np.zeros(len(frequency), dtype=np.float64)
    count = np.zeros(len(frequency), dtype=np.uint16)
    for lo_hz, baseband, power in tiles:
        baseband, power = np.asarray(baseband), np.asarray(power)
        if (not math.isfinite(lo_hz) or not low <= lo_hz <= high
                or baseband.ndim != 1 or len(baseband) < 16 or power.shape != baseband.shape
                or not np.all(np.isfinite(baseband)) or not np.all(np.diff(baseband) > 0)
                or not np.all(np.isfinite(power)) or np.any(power < 0)):
            raise ValueError('Invalid PSD tile')
        target = frequency - lo_hz
        # Stay one native bin inside the requested 20 MHz passband.
        edge = USABLE_HZ / 2 - float(np.max(np.diff(baseband)))
        valid = ((np.abs(target) >= DC_GUARD_HZ) & (np.abs(target) <= edge)
                 & (target >= baseband[0]) & (target <= baseband[-1]))
        total[valid] += np.interp(target[valid], baseband, power)
        if np.any(count[valid] == np.iinfo(count.dtype).max):
            raise ValueError('Too many overlapping tiles')
        count[valid] += 1
    combined = np.full(len(frequency), np.nan, dtype=np.float64)
    np.divide(total, count, out=combined, where=count > 0)
    return frequency, combined, count


def dbfs_per_hz(power):
    """Display floor is -200 dBFS/Hz; missing samples remain NaN."""
    power = np.asarray(power, dtype=np.float64)
    if np.any(np.isinf(power)) or np.any(power < 0):
        raise ValueError('PSD cannot be negative or infinite')
    return 10 * np.log10(np.maximum(power, 1e-20))
