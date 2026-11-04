"""Guard trial must refuse unsafe RF and mismatched registers before sampling."""
from types import SimpleNamespace

import pytest

from src.ps.sentinel.app.monitor_x1_guard8 import configure_checked, check_safety
from src.ps.sentinel.drivers.regs import cfar_x1 as C


def hardware():
    events = []
    regs = {C.CTRL: 1, C.N_SHIFT: 4, C.GUARD: 8, C.ALPHA: 1974,
            C.DC_MASK: 3, C.MIN_WIDTH: 2, C.MERGE_GAP: 6, C.MASK_COUNT: 0,
            C.STATUS: 0}
    regs.update({C.MASK+4*i: 0 for i in range(16)})
    hw = SimpleNamespace(source=SimpleNamespace(stop=lambda: events.append('stop')),
                         src_regs=SimpleNamespace(read=lambda _: 0),
                         enable_processing=lambda **kw: events.append(kw),
                         cfar=SimpleNamespace(mmio=SimpleNamespace(read=regs.__getitem__)),
                         spec=SimpleNamespace(read=lambda _: 3))
    radio = SimpleNamespace(rx_lo=96399998, rate=3840000, tx_atten=(89.75, 89.75))
    return hw, radio, regs, events


def test_stop_configure_readback_before_sampling():
    hw, radio, _, events = hardware()
    assert configure_checked(hw, radio, 96400000)['0x8'] == 8
    assert events[0] == 'stop'
    assert events[1]['guard'] == 8 and events[1]['n'] == 16


@pytest.mark.parametrize('offset', [C.GUARD, C.N_SHIFT, C.ALPHA, C.CTRL, C.MASK+60])
def test_rejects_corrupt_configuration(offset):
    hw, radio, regs, _ = hardware()
    regs[offset] ^= 1
    with pytest.raises(RuntimeError, match='readback'):
        configure_checked(hw, radio, 96400000)


@pytest.mark.parametrize('field,value', [('rx_lo', 96400006), ('rate', 7680000),
                                        ('tx_atten', (30, 30))])
def test_rejects_wrong_radio_before_configure(field, value):
    hw, radio, _, events = hardware()
    setattr(radio, field, value)
    with pytest.raises(RuntimeError):
        configure_checked(hw, radio, 96400000)
    assert events == ['stop']


def test_rejects_source_that_did_not_stop():
    hw, radio, _, events = hardware()
    hw.src_regs.read = lambda _: 1
    with pytest.raises(RuntimeError, match='stopped'):
        configure_checked(hw, radio, 96400000)
    assert events == ['stop']


@pytest.mark.parametrize('change', [{'temperature_c': None}, {'temperature_c': float('nan')},
                                   {'rx_rssi_dbm': float('nan')}, {'rx_rssi_dbm': -29.9},
                                   {'tx_atten_mdb': [30000, 30000]}])
def test_unsafe_readback_aborts(change):
    entry = dict(temperature_c=50, rx_rssi_dbm=-70, tx_atten_mdb=[89750, 89750])
    check_safety(entry)
    entry.update(change)
    with pytest.raises(RuntimeError):
        check_safety(entry)
