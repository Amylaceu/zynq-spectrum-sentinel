"""Atomic raw-cycle snapshots; callers use the loaded image's clock contract."""
import time
from dataclasses import dataclass
from .regs import perf_ctrl as R

@dataclass(frozen=True)
class PerfSnapshot:
    samples: int
    cycles: int
    fft_frames: int
    hits: int
    lists: int
    latency_cycles: int
    markers_done: int
    status: int
    fifo_level: int

class Performance:
    def __init__(self,mmio):
        self.mmio=mmio
        if mmio.read(R.VERSION)!=0x50460001:raise ValueError('Performance IP version mismatch')
    def clear(self):
        self.mmio.write(R.CLEAR_TOKEN,(self.mmio.read(R.CLEAR_TOKEN)+1)&0xffffffff)
    def arm(self):
        # Caller drains previous frames first; exactly one outstanding marker is supported.
        self.mmio.write(R.ARM_TOKEN,(self.mmio.read(R.ARM_TOKEN)+1)&0xffffffff)
    def snapshot(self,timeout=.5):
        token=(self.mmio.read(R.SNAP_ACK)+1)&0xffffffff
        self.mmio.write(R.SNAP_TOKEN,token)
        deadline=time.monotonic()+timeout
        while self.mmio.read(R.SNAP_ACK)!=token:
            if time.monotonic()>=deadline:raise TimeoutError('Performance snapshot timed out')
            time.sleep(.001)
        values=[self.mmio.read(off) for off in (R.SAMPLES_LO,R.SAMPLES_HI,R.CYCLES_LO,R.CYCLES_HI,
            R.FFT_FRAMES,R.HITS,R.LISTS,R.LATENCY_CYCLES,R.MARKERS_DONE,R.STATUS,R.FIFO_LEVEL)]
        if self.mmio.read(R.SNAP_ACK)!=token:raise RuntimeError('Concurrent performance snapshot writer')
        return PerfSnapshot(values[0]|values[1]<<32,values[2]|values[3]<<32,*values[4:])
