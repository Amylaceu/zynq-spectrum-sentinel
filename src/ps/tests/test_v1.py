import pytest
from src.ps.sentinel.v1 import Source,wait_until
from src.ps.sentinel.drivers.regs import src_ctrl as S

class Fake:
    def __init__(self):self.v={S.VERSION:0x53520001};self.writes=[]
    def read(self,o):return self.v.get(o,0)
    def write(self,o,v):self.v[o]=v;self.writes.append((o,v))

def test_v1_explicit_source_config_and_negative_bins():
    f=Fake();s=Source(f);actual=s.configure('test',rate=30720000,bins=(-64,64,300),amplitudes=(4096,4096,4096),frames=1)
    assert actual==30720000 and f.v[S.CTRL]==4
    assert f.v[S.FCW0]==(-64*2097152)&0xffffffff and f.v[S.FCW2]==300*2097152
    assert f.v[S.FRAME_LIMIT]==1 and f.v[S.ARM_TOKEN]==1
    s.start();assert f.v[S.CTRL]==5
    with pytest.raises(RuntimeError):s.configure('rf')
    s.stop();assert f.v[S.CTRL]==4

def test_v1_invalid_configuration_has_no_writes():
    f=Fake();s=Source(f)
    for kw in ({'rate':0},{'bins':(2048,)},{'amplitudes':(-1,)},{'frames':-1}):
        with pytest.raises(ValueError):s.configure('test',**kw)
    assert f.writes==[]
    with pytest.raises(TimeoutError):wait_until(lambda:False,timeout=0)
