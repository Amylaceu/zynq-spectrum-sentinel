import numpy as np
import pytest
from src.ps.sentinel.lcd_framebuffer import rgb332, LcdFramebuffer
from src.ps.sentinel.lcd_spectrum import spectrum, SpectrumScreen


def test_rgb332_channels_and_shape():
    a = np.zeros((240, 400, 3), dtype=np.uint8)
    a[0, :4] = [(255,0,0),(0,255,0),(0,0,255),(255,255,255)]
    assert list(rgb332(a)[0, :4]) == [224,28,3,255]
    with pytest.raises(ValueError): rgb332(a[:2])


def test_spectrum_known_signed_frequency_and_render():
    fs = 30720000
    n = np.arange(8192)
    z = 1000*np.exp(-2j*np.pi*fs/8*n/fs)
    words = np.zeros((8192,4), dtype=np.int16)
    words[:,0] = np.rint(z.real);words[:,1] = np.rint(z.imag)
    f, db = spectrum(words, fs, 98e6)
    assert f[np.argmax(db)] == 98e6-fs/8
    im, packed = SpectrumScreen().draw(f, db, frame=1)
    assert im.size == (400,240) and packed.shape == (240,400)
    assert packed.dtype == np.uint8 and np.ptp(packed)>0


def test_present_writes_inactive_page_before_request_and_checks_ack():
    events=[]
    class Mem:
        length=262144
        def write(self,o,data): events.append(('data',o,len(data)))
        def read(self,o): events.append(('drain',o));return 0
    class Ctrl:
        requested=0
        def read(self,o): return 0x4c430002|self.requested if o==8 else self.requested
        def write(self,o,v): events.append(('request',v));self.requested=v
    lcd=LcdFramebuffer(Mem(),Ctrl())
    assert lcd.present(np.zeros((240,400),dtype=np.uint8))['active_page']==1
    assert events==[('data',131072,96000),('drain',227068),('request',1)]
    with pytest.raises(ValueError):lcd.present(np.zeros((4,4),dtype=np.uint8))


def test_present_refuses_unacknowledged_previous_request():
    class Mem:
        length=262144
        def write(self,*a): raise AssertionError('Must not overwrite an active page')
    class Ctrl:
        def read(self,o):return 0x4c430002 if o==8 else 1
    with pytest.raises(TimeoutError):
        LcdFramebuffer(Mem(),Ctrl()).present(np.zeros((240,400),dtype=np.uint8),timeout_s=.005)
