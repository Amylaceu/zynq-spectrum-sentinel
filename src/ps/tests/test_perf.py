import pytest
from src.ps.sentinel.drivers.perf import Performance
from src.ps.sentinel.drivers.regs import perf_ctrl as R

class Fake:
    def __init__(self):self.v={R.VERSION:0x50460001,R.SNAP_ACK:0xffffffff};self.ack=True;self.race=False
    def read(self,o):return self.v.get(o,0)
    def write(self,o,v):
        self.v[o]=v
        if o==R.SNAP_TOKEN and self.ack:
            self.v.update({R.SNAP_ACK:v,R.SAMPLES_LO:0xffffffff,R.SAMPLES_HI:2,R.CYCLES_LO:5,R.CYCLES_HI:1,
                R.FFT_FRAMES:7,R.HITS:11,R.LISTS:7,R.LATENCY_CYCLES:123,R.MARKERS_DONE:1,R.STATUS:4,R.FIFO_LEVEL:3})

def test_perf_atomic_snapshot_and_64bit_values():
    f=Fake();p=Performance(f);p.clear();p.arm();s=p.snapshot()
    assert f.v[R.SNAP_TOKEN]==0 and f.v[R.CLEAR_TOKEN]==f.v[R.ARM_TOKEN]==1
    assert s.samples==0x2ffffffff and s.cycles==0x100000005
    assert (s.fft_frames,s.hits,s.lists,s.latency_cycles,s.markers_done,s.status,s.fifo_level)==(7,11,7,123,1,4,3)

def test_perf_timeout_and_wrong_hardware():
    f=Fake();p=Performance(f);f.ack=False
    with pytest.raises(TimeoutError):p.snapshot(timeout=0)
    f.v[R.VERSION]=0
    with pytest.raises(ValueError):Performance(f)
