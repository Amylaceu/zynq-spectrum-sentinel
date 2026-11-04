"""Keep ownership through fault cleanup and reject post-drain errors."""
from types import SimpleNamespace
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sentinel.app.monitor_x2 import check_processing, check_rssi_owned
from sentinel.app.runtime_v1 import Session
from sentinel.rf.safety import TxGuard


def test_rssi_fault_keeps_radio_owned_until_source_stopped():
    events = []
    radio = SimpleNamespace(guard=TxGuard(),
        rssi=lambda channel: -29 if channel == 1 else -60,
        close=lambda: events.append('close_radio'))
    session = Session('unused')
    session._owns_hardware = True
    session.radio = radio
    session.hw = SimpleNamespace(source=SimpleNamespace(stop=lambda: events.append('stop_source')))
    with pytest.raises((RuntimeError, PermissionError)):
        try:
            check_rssi_owned(radio)
        finally:
            session.close()
    assert events == ['stop_source', 'close_radio']


@pytest.mark.parametrize('perf,lcd,cfar', [(1, 0, 0), (0, 4, 0), (0, 0, 4)])
def test_drain_status_errors_rejected(perf, lcd, cfar):
    hw = SimpleNamespace(lcd=SimpleNamespace(registers=SimpleNamespace(read=lambda _: lcd)),
                         cfar=SimpleNamespace(mmio=SimpleNamespace(read=lambda _: cfar)))
    with pytest.raises(RuntimeError, match='processing'):
        check_processing(hw, SimpleNamespace(status=perf))
