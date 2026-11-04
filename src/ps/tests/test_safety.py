import pytest
from src.ps.sentinel.rf.safety import TxGuard
from src.ps.sentinel.rf.ad9361 import AD9361

def test_guard_limits_and_no_implicit_cable_confirmation():
    guard=TxGuard()
    for v in (29.75,float('nan'),float('inf'),90):
        with pytest.raises(PermissionError):guard.check(v)
    assert guard.check(30)==30
    with pytest.raises(PermissionError):guard.set_mode('cable')
    assert guard.mode=='air'
    guard.set_mode('cable',True);assert guard.check(10)==10
    with pytest.raises(PermissionError):guard.check(9.75)

class Fake:
    def __init__(self):self.writes=[];self.closed=False
    def z20_ad9361_open(self):return 0
    def z20_set_tx_attenuation(self,v):self.writes.append(v);return 0
    def z20_configure_receive(self,*args):return 0
    def z20_ad9361_close(self):self.closed=True
    def z20_get_rx_rssi(self,ch,out):out._obj.value=-29000;return 0

def test_exception_closes_and_restores_maximum_attenuation():
    f=Fake();radio=AD9361(backend=f)
    with pytest.raises(ValueError):
        with radio:
            with pytest.raises(PermissionError):radio.tx_atten=29.75
            raise ValueError('injected failure')
    assert f.closed and f.writes==[89750,89750]
    radio.close();assert f.writes==[89750,89750]

def test_rssi_limit_stops_and_resets():
    f=Fake();radio=AD9361(backend=f).open()
    with pytest.raises(PermissionError):radio.check_rssi()
    assert f.closed and f.writes[-1]==89750
