"""Exact integer DDS/capture supplement; does not change the floating PFB API."""
import numpy as np


def sine_table():
    """Signed18 Q1.16, full +1, nearest-even; phase truncates to 12 bits."""
    return np.rint(np.sin(2 * np.pi * np.arange(4096) / 4096) * 65536).astype(np.int64)


def nco_mix_fixed(iq, fcw):
    x = np.asarray(iq)
    if x.ndim != 2 or x.shape[1] != 2 or not np.issubdtype(x.dtype, np.integer):
        raise ValueError("Expected integer N x 2 IQ")
    if np.any(x < -32768) or np.any(x > 32767) or not 0 <= fcw < 2**32:
        raise ValueError("IQ or FCW out of range")
    x = x.astype(np.int64)
    phase = (np.arange(len(x), dtype=np.uint64) * fcw) & 0xffffffff
    index = (phase >> 20).astype(np.int64)
    table = sine_table()
    s, c = table[index], table[(index + 1024) & 4095]
    mixed = np.column_stack((x[:, 0]*c + x[:, 1]*s, x[:, 1]*c - x[:, 0]*s))
    return np.clip(mixed >> 16, -32768, 32767).astype(np.int16)


def scap_words(iq, fcw, channel, timestamp=0, src=0, dec=1):
    if dec != 1 or not 0 <= channel < 16 or not 1 <= len(iq) <= 4096:
        raise ValueError("Only DEC=1, channels 0..15, lengths 1..4096")
    if not 0 <= timestamp < 2**64 or not 0 <= src < 2**32:
        raise ValueError("Timestamp or source out of range")
    mixed = nco_mix_fixed(iq, fcw)
    header = [0x53434150, timestamp & 0xffffffff, timestamp >> 32, channel,
              fcw, dec, len(iq), src]
    packed = mixed[:, 0].astype(np.uint16).astype(np.uint32)
    packed |= mixed[:, 1].astype(np.uint16).astype(np.uint32) << 16
    return np.r_[np.asarray(header, dtype=np.uint32), packed]
