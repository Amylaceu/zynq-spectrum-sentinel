"""Atomic X2 stream statistics, compatible with board Python 3.8."""
from dataclasses import dataclass
import time

from ..regs import stream_x2 as R

VERSION_VALUE = 0x58320001


@dataclass(frozen=True)
class StreamSnapshot:
    sample_drop: int
    frame_drop: int
    frames_in: int
    frames_out: int
    status: int
    fifo_level: int
    token: int

    def require_lossless(self):
        # Check absolute counters, including losses before the measurement
        # window. No baseline subtraction can hide initialization failures.
        if self.sample_drop or self.status:
            raise RuntimeError('ADC loss or stream framing error: ' + repr(self))
        if any(v == 0xffffffff for v in
               (self.sample_drop, self.frame_drop, self.frames_in, self.frames_out)):
            raise RuntimeError('Saturated stream counter')
        if self.frames_out + self.frame_drop > self.frames_in:
            raise RuntimeError('Stream frame conservation failed')
        if not 0 <= self.fifo_level <= 4096:
            raise RuntimeError('Invalid ADC FIFO occupancy')

    def require_monotonic(self, previous):
        for name in ('sample_drop', 'frame_drop', 'frames_in', 'frames_out'):
            if getattr(self, name) < getattr(previous, name):
                raise RuntimeError('Stream counter reset/decrease: ' + name)


class StreamStatistics:
    def __init__(self, mmio):
        self.mmio = mmio
        if mmio.read(R.VERSION) != VERSION_VALUE:
            raise ValueError('X2 stream statistics version mismatch')

    def snapshot(self, timeout=.5):
        token = (self.mmio.read(R.SNAP_ACK) + 1) & 0xffffffff
        self.mmio.write(R.SNAP_TOKEN, token)
        deadline = time.monotonic() + timeout
        while self.mmio.read(R.SNAP_ACK) != token:
            if time.monotonic() >= deadline:
                raise TimeoutError('X2 stream snapshot timed out')
            time.sleep(.001)
        values = [self.mmio.read(off) for off in
                  (R.SAMPLE_DROP, R.FRAME_DROP, R.FRAMES_IN, R.FRAMES_OUT,
                   R.STATUS, R.FIFO_LEVEL)]
        if self.mmio.read(R.SNAP_ACK) != token or self.mmio.read(R.SNAP_TOKEN) != token:
            raise RuntimeError('Concurrent X2 statistics snapshot writer')
        return StreamSnapshot(*values, token=token)
