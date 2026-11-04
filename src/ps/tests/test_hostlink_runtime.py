"""Verify raw power units and capture lease cleanup with fake MMIO only."""
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sentinel.app.hostlink_runtime import RuntimeLink, power_packet
from sentinel.app.hostlink import Hostlink


def test_power_max_pair_and_reference():
    values = np.ones(2048, dtype='<u4')
    values[1] = 100
    values[2:4] = (10, 1000)
    result = np.frombuffer(power_packet(values), dtype='<i2')
    assert result.shape == (1024,)
    assert list(result[:3]) == [2000, 3000, 0]
    with pytest.raises(ValueError):
        power_packet(np.ones(1024, dtype=np.uint32))


class CaptureControl:
    def __init__(self):
        self.token = 0
    def read(self, offset):
        return self.token


def test_sampler_stops_before_return_and_snapshot_hash(tmp_path, monkeypatch):
    # Preserve the real constructor while using ephemeral loopback ports.
    import sentinel.app.hostlink_runtime as adapter
    real_read = Path.read_text
    monkeypatch.setattr(Path, 'read_text', lambda p, *a, **k:
        'fake-boot' if str(p).endswith('boot_id') else real_read(p, *a, **k))
    monkeypatch.setattr(adapter, 'Hostlink', lambda *a, **k: Hostlink(
        '127.0.0.1', a[1], mode=k['mode'], allow_loopback=True, tcp_port=0, http_port=0))
    control = CaptureControl()
    arm_calls = []
    def arm():
        control.token ^= 1
        arm_calls.append(time.monotonic())
        return control.token
    hw = SimpleNamespace(arm_capture=arm, capture_ctrl=control,
        capture=SimpleNamespace(array=np.arange(2048, dtype='<u4')),
        lcd=SimpleNamespace(registers=SimpleNamespace(read=lambda offset: len(arm_calls))))
    bit = tmp_path/'fake.bit'
    bit.write_bytes(b'fake')
    with RuntimeLink(hw, bit, tmp_path, 96400000, address='unused-test') as link:
        time.sleep(.23)
        assert link.samples >= 2
        directory = tmp_path/link.snapshot()
        assert (directory/'samples.npz.sha256').exists()
        with link.paused():
            count = len(arm_calls)
            time.sleep(.12)
            assert len(arm_calls) == count
    count = len(arm_calls)
    time.sleep(.12)
    assert len(arm_calls) == count
    assert not link.thread.is_alive()
    assert (tmp_path/'hostlink.json.sha256').exists()


def test_classification_truth_is_per_capture_only():
    published=[]
    link=RuntimeLink.__new__(RuntimeLink)
    link.service=SimpleNamespace(publish=lambda *a,**k: published.append((a,k)))
    link.selected=None
    link.last_iq=0
    link.classification(dict(track=1,prediction='FM',transmitted='QPSK',score=.7,
        top5=[dict(label='FM',score=.7)],top5_scope='coarse8_softmax'),np.ones(512,dtype='<c8'))
    assert published[0][1]['transmitted']=='QPSK'
    assert published[0][1]['top5'] == [dict(label='FM',score=.7)]
    assert published[0][1]['top5_scope'] == 'coarse8_softmax'
    link.classification(dict(track=1,prediction='FM',score=.7),np.ones(512,dtype='<c8'))
    assert 'transmitted' not in published[-1][1]
