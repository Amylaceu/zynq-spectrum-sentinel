import struct
import pytest
from src.ps.sentinel.drivers.cfar import Cfar
from src.ps.sentinel.drivers.regs import cfar_ctrl as R


class MMIO:
    def __init__(self):
        self.values={R.VERSION:0x43460001,R.FRAME_COUNT:8,R.TARGET_COUNT:1}
        raw=struct.pack('<HHHHII',10,14,12,1,0xffffffff,0xffffffff)
        self.values.update({R.TARGETS+4*j:struct.unpack_from('<I',raw,4*j)[0] for j in range(4)})
        self.writes=[];self.racing=False
    def read(self,offset):
        if self.racing and offset==R.FRAME_COUNT:
            self.values[offset]+=1
        return self.values.get(offset,0)
    def write(self,offset,value):
        self.writes.append((offset,value));self.values[offset]=value


def test_list_binary_contract_and_sequence_race():
    m=MMIO();c=Cfar(m);sequence,targets=c.targets()
    assert sequence==8 and targets[0].peak_bin==12 and targets[0].flags==1
    assert targets[0].peak_power==targets[0].sum_power==0xffffffff
    m.racing=True
    with pytest.raises(RuntimeError,match='changed'):c.targets()


def test_reject_invalid_configuration_without_writing():
    m=MMIO();c=Cfar(m)
    for kw in ({'n':3},{'n':128},{'guard':32},{'alpha':65536},{'dc_mask':255},{'gap':-1},{'mode':'BAD'}):
        with pytest.raises(ValueError):c.configure(**kw)
    assert m.writes==[]
    m.values[R.STATUS]=1
    with pytest.raises(RuntimeError):c.configure()
    assert m.writes==[]


def test_coherent_occupancy_requires_disabled_idle():
    m=MMIO();c=Cfar(m);m.values[R.CTRL]=1
    with pytest.raises(RuntimeError):c.occupancy()
    m.values[R.CTRL]=0;m.values[R.OCC_FRAMES]=100;m.values[R.OCCUPANCY+4*19]=65535
    frames,counters=c.occupancy()
    assert frames==100 and counters[19]==65535 and sum(counters)==65535
    m.values[R.TARGET_COUNT]=33
    with pytest.raises(ValueError,match='count'):c.targets()


def test_unsupported_version_and_malformed_target_rejected():
    m=MMIO();m.values[R.VERSION]=0
    with pytest.raises(ValueError,match='version'):Cfar(m)
    m.values[R.VERSION]=0x43460001;c=Cfar(m);m.values[R.TARGETS+4]=9999
    with pytest.raises(ValueError,match='interval'):c.targets()


def test_mapped_target_window_burst_still_checks_frame_sequence():
    import numpy as np
    m=MMIO();m.array=np.zeros(4096,dtype=np.uint32)
    m.array[R.TARGETS//4:R.TARGETS//4+4]=[m.values[R.TARGETS+4*i] for i in range(4)]
    sequence,targets=Cfar(m).targets()
    assert sequence==8 and targets[0].peak_bin==12
    m.racing=True
    with pytest.raises(RuntimeError,match='changed'):Cfar(m).targets()
