import numpy as np
import pytest
from src.ps.sentinel.lcd_direct import pack_ui,DirectLCD,draw_ui
from src.ps.sentinel.drivers.regs import lcd_ctrl as R
from src.ps.sentinel.drivers.cfar import Target


class MMIO:
    def __init__(self,registers=False):
        self.values={R.VERSION:0x4c430001} if registers else {}
        self.writes=[]
    def read(self,offset):return self.values.get(offset,0)
    def write(self,offset,value):self.values[offset]=value;self.writes.append((offset,value))


def test_two_bit_layout_region_boundary_and_padding():
    top=np.resize(np.arange(4,dtype=np.uint8),(160,240));bottom=np.full((80,800),2,dtype=np.uint8)
    words=pack_ui(top,bottom)
    assert len(words)==8192 and words.dtype==np.uint32
    assert words[0]==0xe4e4e4e4 and words[2399]==0xe4e4e4e4
    assert words[2400]==words[6399]==0xaaaaaaaa and not words[6400:].any()
    with pytest.raises(ValueError):pack_ui(top*2,bottom)
    with pytest.raises(ValueError):pack_ui(top.astype(float),bottom)


def test_ui_ownership_token_readback_and_phase_bounds():
    regs=MMIO(True);memory=MMIO();lcd=DirectLCD(regs,memory)
    arrays=(np.zeros((160,240),dtype=np.uint8),np.ones((80,800),dtype=np.uint8))
    assert lcd.submit_ui(*arrays)==1 and len(memory.writes)==8192
    with pytest.raises(RuntimeError,match='still'):lcd.submit_ui(*arrays)
    assert len(memory.writes)==8192
    regs.values[R.UI_APPLIED]=1;lcd.wait_ui(1)
    regs.values[R.STATUS]=4
    with pytest.raises(RuntimeError,match='error'):lcd.submit_ui(*arrays)
    for n in (0,256,-1,1.5):
        with pytest.raises(ValueError):lcd.set_bus_phase(n)
    with pytest.raises(TimeoutError):lcd.wait_ui(2,timeout=0)


def test_ui_pages_and_binary_glyph_palette():
    targets=[Target(100+i*80,103+i*80,101+i*80,0,100000,200000) for i in range(13)]
    first=draw_ui(targets,98e6,30.72e6,page=0)
    last=draw_ui(targets,98e6,30.72e6,page=2)
    assert first[0].shape==(160,240) and first[1].shape==(80,800)
    assert set(np.unique(first[0]))<={0,1,2,3} and set(np.unique(first[1]))<={0,1,2,3}
    assert not np.array_equal(first[0],last[0])


def test_temperature_status_is_rendered_or_marked_unknown():
    missing=draw_ui([],98e6,3.84e6,temperature_c=None)[1]
    present=draw_ui([],98e6,3.84e6,temperature_c=47.2)[1]
    assert not np.array_equal(missing[56:78],present[56:78])
