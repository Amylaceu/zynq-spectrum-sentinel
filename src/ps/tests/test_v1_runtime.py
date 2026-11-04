import io,sys,types
import numpy as np
import pytest
from src.ps.sentinel.app import runtime_v1 as M
from src.ps.sentinel.app import selftest_v1 as T

class Source:
    def __init__(self):self.stops=0
    def stop(self):self.stops+=1
    def configure(self,*a,**kw):pass
    def start(self):pass

class GPIO:
    def __init__(self):self.values={0:0xffff,4:0xffffffff};self.writes=[]
    def read(self,offset):return self.values[offset]
    def write(self,offset,value):
        if offset==0:self.values[offset]=value
        self.writes.append((offset,value))

class HW:
    def __init__(self,*a,**kw):
        self.source=Source();self.overlay=types.SimpleNamespace(is_loaded=lambda:True);self.gpio=GPIO()
        self.checked=types.SimpleNamespace(registers=lambda name:self.gpio)

class Radio:
    def __init__(self):self.closed=False;self.tx_atten=(89.75,89.75)
    def open(self,**kw):return self
    def close(self):self.closed=True

def test_session_test_mode_never_opens_radio(monkeypatch):
    monkeypatch.setitem(sys.modules,'fcntl',types.SimpleNamespace(LOCK_EX=1,LOCK_NB=2,LOCK_UN=8,flock=lambda *a:None))
    lock=io.StringIO();monkeypatch.setattr(M,'open',lambda *a:lock,raising=False)
    monkeypatch.setattr(M,'V1',HW)
    monkeypatch.setattr(M,'AD9361',lambda:pytest.fail('RF must stay in reset in source=test'))
    session=M.Session('fake',source='test')
    with pytest.raises(RuntimeError):
        with session:raise RuntimeError('forced abort')
    assert session.hw.source.stops==1 and session.hw.gpio.values[0]==0 and lock.closed
    assert session.hw.gpio.values[4]==0xffffffff
    assert all(offset==0 for offset,_ in session.hw.gpio.writes)

def test_session_releases_lock_after_bad_artifact(monkeypatch):
    monkeypatch.setitem(sys.modules,'fcntl',types.SimpleNamespace(LOCK_EX=1,LOCK_NB=2,LOCK_UN=8,flock=lambda *a:None))
    lock=io.StringIO();monkeypatch.setattr(M,'open',lambda *a:lock,raising=False)
    def bad(*a,**kw):raise ValueError('bad bit')
    monkeypatch.setattr(M,'V1',bad)
    with pytest.raises(ValueError):M.Session('fake').__enter__()
    assert lock.closed

class Owner(np.ndarray):
    def __new__(cls,n):
        obj=np.zeros(n,dtype=np.uint8).view(cls);obj.freed=False;obj.physical_address=0x100000;return obj
    def flush(self):pass
    def invalidate(self):pass
    def freebuffer(self):self.freed=True

class DMA:
    def __init__(self):self.writes=[]
    def write(self,a,v):self.writes.append((a,v))
    def read(self,a):return 2 if a==4 else 0

class CaptureHW:
    def __init__(self):
        self.source=Source();self.dma=DMA();self.frames=0
        self.cfar=types.SimpleNamespace(mmio=types.SimpleNamespace(read=lambda a:0 if a==0x34 else self.frames),targets=lambda:(self.frames,[]))
        self.checked=types.SimpleNamespace(registers=lambda n:self.dma)
        self.perf=types.SimpleNamespace(snapshot=lambda:types.SimpleNamespace(status=0))
    def arm_capture(self):return 1
    def read_capture(self,t):self.frames+=1;return np.zeros(2048,dtype=np.uint32)

def test_finite_replay_dma_reset_before_release_even_on_capture_error(monkeypatch):
    owner=Owner(8320);h=CaptureHW();monkeypatch.setattr(T,'allocate_owned',lambda n:owner)
    power,_,_=T.finite_frame(h,'replay',replay=np.arange(2048,dtype=np.uint32))
    assert len(power)==2048 and owner.freed and h.dma.writes[-1]==(0,4)
    assert (0x28,8192) in h.dma.writes and (0x18,0x100040) in h.dma.writes
    owner=Owner(8320);monkeypatch.setattr(T,'allocate_owned',lambda n:owner)
    def fail(t):raise IOError('capture failed')
    h.read_capture=fail
    with pytest.raises(IOError):T.finite_frame(h,'replay',replay=np.arange(2048,dtype=np.uint32))
    assert owner.freed and h.dma.writes[-1]==(0,4)


def test_rf_session_closes_muted_radio_on_format_failure(monkeypatch):
    monkeypatch.setitem(sys.modules,'fcntl',types.SimpleNamespace(LOCK_EX=1,LOCK_NB=2,LOCK_UN=8,flock=lambda *a:None))
    lock=io.StringIO();monkeypatch.setattr(M,'open',lambda *a:lock,raising=False)
    radio=Radio();monkeypatch.setattr(M,'AD9361',lambda:radio)
    class BadADC:
        def write(self,*a):pass
        def read(self,*a):return 0
    class RfHW(HW):
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw)
            self.checked=types.SimpleNamespace(registers=lambda n:self.gpio if n=='axi_ad9361_gpio' else BadADC())
    monkeypatch.setattr(M,'V1',RfHW)
    session=M.Session('fake',source='rf')
    with pytest.raises(RuntimeError,match='format'):session.__enter__()
    assert radio.closed and session.hw.source.stops==1 and session.hw.gpio.values[0]==0 and lock.closed


def test_session_rejects_rf_gpio_reset_readback_failure(monkeypatch):
    monkeypatch.setitem(sys.modules,'fcntl',types.SimpleNamespace(LOCK_EX=1,LOCK_NB=2,LOCK_UN=8,flock=lambda *a:None))
    lock=io.StringIO();monkeypatch.setattr(M,'open',lambda *a:lock,raising=False)
    class BadGPIO(GPIO):
        def read(self,offset):return 1
    class BadGPIOHW(HW):
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw);self.gpio=BadGPIO()
            self.checked=types.SimpleNamespace(registers=lambda name:self.gpio)
    monkeypatch.setattr(M,'V1',BadGPIOHW)
    with pytest.raises(RuntimeError,match='reset readback'):
        with M.Session('fake',source='test'):
            pass
    assert lock.closed


def test_rf_handoff_failure_does_not_touch_another_owner(monkeypatch):
    monkeypatch.setitem(sys.modules,'fcntl',types.SimpleNamespace(LOCK_EX=1,LOCK_NB=2,LOCK_UN=8,flock=lambda *a:None))
    lock=io.StringIO();monkeypatch.setattr(M,'open',lambda *a:lock,raising=False)
    monkeypatch.setattr(M,'V1',HW)
    class BusyRadio(Radio):
        def open(self,**kw):raise BlockingIOError('RF is owned by another process')
    monkeypatch.setattr(M,'AD9361',BusyRadio)
    session=M.Session('fake',source='rf')
    with pytest.raises(BlockingIOError):session.__enter__()
    assert session.hw.source.stops==0
    assert session.hw.gpio.writes==[(0,0)]
    assert lock.closed


def test_session_close_is_idempotent_after_ownership_release(monkeypatch):
    monkeypatch.setitem(sys.modules,'fcntl',types.SimpleNamespace(LOCK_EX=1,LOCK_NB=2,LOCK_UN=8,flock=lambda *a:None))
    lock=io.StringIO();monkeypatch.setattr(M,'open',lambda *a:lock,raising=False)
    monkeypatch.setattr(M,'V1',HW)
    with M.Session('fake',source='test') as session:
        pass
    writes=list(session.hw.gpio.writes)
    session.close()
    assert session.hw.source.stops==1 and session.hw.gpio.writes==writes
