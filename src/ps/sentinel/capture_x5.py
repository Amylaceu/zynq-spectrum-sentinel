"""X5 PL PFB/NCO single-shot capture, with DMA ownership and packet checks.

Importing this module never touches hardware. DEC=1 at the accepted 3.84 MSPS
input gives 480 kSPS. No software resampling or substitution is performed.
"""
from dataclasses import dataclass
import math
import time

import numpy as np

from .dma import XilinxDma, _retain_for_reset


MAGIC = 0x53434150
CHANNEL_RATE = 480000
SAMPLES = 4096
PACKET_BYTES = (8 + SAMPLES) * 4


@dataclass(frozen=True)
class Selection:
    channel: int
    fcw: int
    offset_hz: float
    residual_hz: float


def select_channel(offset_hz, rate_hz=3840000):
    """Nearest natural-order PFB bin; positive FCW removes positive residual."""
    if rate_hz != 3840000 or not math.isfinite(offset_hz):
        raise ValueError('X5 baseline requires 3.84 MSPS and a finite offset')
    if not -rate_hz/2 <= offset_hz < rate_hz/2:
        raise ValueError('Target is outside the Nyquist interval')
    spacing = rate_hz / 16
    signed_bin = math.floor(offset_hz / spacing + .5)
    residual = offset_hz - signed_bin * spacing
    fcw = round(residual / CHANNEL_RATE * 2**32) & 0xffffffff
    return Selection(signed_bin % 16, fcw, float(offset_hz), residual)


def decode_packet(words, selection, source):
    a = np.asarray(words)
    if a.dtype != np.dtype('uint32') or a.shape != (8+SAMPLES,):
        raise ValueError('SCAP packet must contain exactly 4104 uint32 words')
    if (int(a[0]) != MAGIC or int(a[3]) != selection.channel or
            int(a[4]) != selection.fcw or int(a[5]) != 1 or
            int(a[6]) != SAMPLES or int(a[7]) != source):
        raise ValueError('SCAP header/configuration mismatch')
    i = (a[8:] & 65535).astype(np.uint16).view(np.int16).astype(np.float32)
    q = (a[8:] >> 16).astype(np.uint16).view(np.int16).astype(np.float32)
    return {'iq': (i + 1j*q)/32768, 'timestamp_cycles': int(a[1]) | int(a[2]) << 32,
            'fs_hz': CHANNEL_RATE, 'channel': selection.channel,
            'fcw': selection.fcw, 'source': source, 'raw_words': a.copy()}


class ChannelCapture:
    """All control GPIOs must run on the 150 MHz DSP AXI clock converter.

    A timed-out allocation remains quarantined until a documented PL reset.
    This object becomes unusable after ANY failed transfer; do not rearm it.
    """
    def __init__(self, control, meta, status, dma, health, allocator=None):
        self.control, self.meta, self.status = control, meta, status
        self.engine = XilinxDma(dma, **({'allocator': allocator} if allocator else {}))
        self.health = health
        self.failed = False

    def acquire(self, selection, source=0, timeout_s=2.0):
        if self.failed:
            raise RuntimeError('Capture requires hardware reset after an earlier failure')
        if not isinstance(source, int) or not 0 <= source <= 0xffffffff or timeout_s <= 0:
            raise ValueError('Invalid source/timeout')
        if not isinstance(selection, Selection) or not 0 <= selection.channel < 16 or not 0 <= selection.fcw <= 0xffffffff:
            raise ValueError('Invalid PFB/NCO selection')
        initial = int(self.status.read(0))
        if initial & 0x1f1:
            raise RuntimeError('PFB/capture busy or sticky fault: %#x' % initial)
        previous = int(self.control.read(0)) & 1
        if ((initial >> 1) & 1) != previous:
            raise RuntimeError('Previous ARM has not completed')
        before = self.health()
        if before:
            raise RuntimeError('Upstream processing is not healthy: %r' % (before,))
        token = previous ^ 1
        config = (SAMPLES << 16) | (1 << 8) | (selection.channel << 4)
        self.control.write(8, selection.fcw)
        self.meta.write(0, source)
        self.control.write(0, config | previous)
        if (self.control.read(8) != selection.fcw or self.meta.read(0) != source or
                self.control.read(0) != (config | previous)):
            raise IOError('Capture configuration readback mismatch')
        # Receiving MUST be primed before ARM; recv() followed by ARM deadlocks.
        buf = self.engine.allocator(PACKET_BYTES)
        self.engine.inflight.append(buf)
        try:
            self.engine.dma.recvchannel.transfer(buf)
            self.control.write(0, config | token)
            self.engine._wait(self.engine.dma.recvchannel, 0x34, 0x30, timeout_s)
            if hasattr(buf, 'invalidate'):
                buf.invalidate()
            # PYNQ's wait() normally populates transferred. We poll with a
            # deadline, so inspect S2MM_LENGTH directly after successful IOC.
            actual = int(self.engine.dma.mmio.read(0x58))
            if actual != PACKET_BYTES:
                raise IOError('Truncated/oversized DMA packet: %d' % actual)
            deadline = time.monotonic() + timeout_s
            while True:
                state = int(self.status.read(0))
                if state & 0x1f0:
                    raise RuntimeError('PFB/NCO fault: %#x' % state)
                if not (state & 1) and ((state >> 1) & 1) == token:
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError('Capture completion toggle timed out')
                time.sleep(.0001)
            if ((state >> 16) & 8191) != SAMPLES or self.health() != before:
                raise RuntimeError('Capture sample count or upstream continuity changed')
            result = decode_packet(np.asarray(buf).view(np.uint32).copy(), selection, source)
        except BaseException:
            self.failed = True
            _retain_for_reset(self.engine.inflight)
            self.engine.dma.mmio.write(0x30, 0)
            raise
        else:
            self.engine.inflight.clear()
            buf.freebuffer()
            return result
