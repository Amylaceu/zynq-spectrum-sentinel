"""Bounded LCD twin wire codec. Frozen pack_ui and X5LCD remain untouched."""
import hashlib
import zlib

import numpy as np

from .lcd_x5 import BANK_WORDS, USED_WORDS, pack_ui

UI_BYTES = USED_WORDS*4
PS_PALETTE = np.array([0x0000, 0xffff, 0xffe0, 0x07ff], dtype=np.uint16)


def decompress_exact(payload, count):
    decoder = zlib.decompressobj()
    raw = decoder.decompress(payload, count+1)
    if len(raw) != count or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError('Invalid bounded compressed frame')
    return raw


def unpack_ui(payload):
    words = np.frombuffer(decompress_exact(payload, UI_BYTES), dtype='<u4')
    pixels = ((words[:, None] >> (2*np.arange(16, dtype=np.uint32))) & 3).astype(np.uint8).ravel()
    return pixels[:96000].reshape(400, 240), pixels[96000:].reshape(80, 800)


def ui_layer(payload):
    right, status = unpack_ui(payload)
    output = np.full((480, 800), 0xf81f, dtype=np.uint16)
    output[:400, 560:] = PS_PALETTE[right]
    output[400:] = PS_PALETTE[status]
    return output


def submitted_frame(lcd, right, status, epoch, readback=False):
    """Read the active bank immediately after APPLIED, before the next submit.

    On readback epochs send the actual bank bytes, after full-word comparison.
    All other epochs send the exact deterministic pack_ui representation.
    """
    words = pack_ui(right, status).astype('<u4', copy=False)
    raw = words.tobytes()
    fields = dict(epoch=int(epoch), words=USED_WORDS, codec='zlib-u32le-2bpp',
                  sha256=hashlib.sha256(raw).hexdigest(), readback_verified=False)
    if readback:
        offset = (epoch & 1)*BANK_WORDS
        if hasattr(lcd.ui_memory, 'array'):
            observed = np.asarray(lcd.ui_memory.array[offset:offset+USED_WORDS], dtype='<u4').copy()
        else:
            observed = np.array([lcd.ui_memory.read(4*(offset+i)) for i in range(USED_WORDS)], dtype='<u4')
        if not np.array_equal(words, observed):
            raise IOError('Full LCD twin bank readback mismatch')
        raw = observed.tobytes()
        fields.update(readback_verified=True, readback_sha256=hashlib.sha256(raw).hexdigest())
    return zlib.compress(raw, 1), fields


def power_q88(power):
    """Same leading-one/LUT rounding as sim.golden.spectrum.to_db_q88.

    Kept numpy-only on PYNQ; importing the FFT reference would pull in scipy.
    """
    p = np.asarray(power)
    if p.shape != (2048,) or p.dtype.kind != 'u' or np.any(p > 0xffffffff):
        raise ValueError('Expected 2048 uint32 power words')
    value = p.astype(np.uint64)
    exponent = np.zeros(2048, dtype=np.int64)
    remaining = value.copy()
    for shift in (16, 8, 4, 2, 1):
        chosen = remaining >= (1 << shift)
        exponent[chosen] += shift
        remaining[chosen] >>= shift
    mantissa = np.empty_like(value)
    high = exponent >= 8
    mantissa[high] = value[high] >> (exponent[high]-8).astype(np.uint64)
    mantissa[~high] = value[~high] << (8-exponent[~high]).astype(np.uint64)
    lut = np.rint(10*np.log10(1+np.arange(256)/256)*65536).astype(np.int64)
    index = np.clip(mantissa.astype(np.int64)-256, 0, 255)
    q = ((exponent*int(round(10*np.log10(2)*65536))+lut[index]+128) >> 8).astype('<i2')
    q[value == 0] = -32768
    edges = np.arange(561)*2048//560
    return np.maximum.reduceat(q, edges[:-1]).astype('<i2')
