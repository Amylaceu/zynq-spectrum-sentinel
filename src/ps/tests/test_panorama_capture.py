"""Capture plan, abort, and baseline recovery contracts without hardware."""
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sentinel import panorama_capture as capture


def test_antenna_and_plan_gate():
    with pytest.raises(PermissionError):
        capture.validate_request('A', False)
    with pytest.raises(ValueError):
        capture.validate_request('B', True)
    with pytest.raises(ValueError):
        capture.validate_request('A', True, 0)
    assert len(capture.validate_request('A', True)) == 55
    assert capture.validate_request('A', True, 1) == [75000000]


class Radio:
    def __init__(self):
        self.configurations = []
        self.lo = 96050000
        self.rate = 3840000

    def configure(self, lo, rate, bandwidth):
        self.lo, self.rate = lo, rate
        self.configurations.append((lo, rate, bandwidth))


@pytest.mark.parametrize('profile,keep_iq', [('legacy', False), ('fast', False), ('fast', True)])
def test_finite_scan_restores_baseline_and_records_gaps(tmp_path, monkeypatch, profile, keep_iq):
    monkeypatch.setattr(capture.time, 'sleep', lambda _: None)
    radio = Radio()
    state = lambda _: dict(lo_hz=radio.lo, rate_hz=radio.rate, rssi_dbm=-80,
                           attenuation_db=[89.75, 89.75], ensm_mode=1)
    monkeypatch.setattr(capture, 'radio_state', state)
    mmio = SimpleNamespace(read=lambda _: 0)
    hw = SimpleNamespace(src_regs=mmio, checked=SimpleNamespace(registers=lambda _: mmio),
                         perf=SimpleNamespace(snapshot=lambda: SimpleNamespace(status=2)),
                         prepare_receive=lambda: dict(restored=True))
    words = np.zeros((8192, 4), dtype='<i2')
    calls = []
    def receive(samples=131072):
        calls.append(1)
        return words, dict(guards_ok=True)
    snapshots = SimpleNamespace(capture=receive, stop=lambda: False)
    result = capture.scan_session(SimpleNamespace(radio=radio, hw=hw), tmp_path, 'A',
                                  [75000000], snapshots, profile=profile, keep_iq=keep_iq)
    assert result['status'] == 'PASS_SNAPSHOT_SCAN'
    assert len(calls) == 2  # mandatory discard, then retained snapshot
    assert result['continuous_integrity_certified'] is False
    assert result['full_group'] is False and result['missing_bins'] > 0
    assert radio.configurations[-1] == (96050000, 3840000, 1500000)
    assert (tmp_path/'tile_000.npz.sha256').exists()
    with np.load(tmp_path/'tile_000.npz') as values:
        assert ('rx1_iq_counts' in values) == (keep_iq or profile == 'legacy')
    assert result['samples_per_tile'] == (65536 if profile == 'fast' else 131072)


@pytest.mark.parametrize('quarantine', [False, True])
def test_capture_failure_preserves_failure_and_dma_ownership(tmp_path, monkeypatch, quarantine):
    monkeypatch.setattr(capture.time, 'sleep', lambda _: None)
    radio = Radio()
    monkeypatch.setattr(capture, 'radio_state', lambda _: dict(lo_hz=radio.lo, rate_hz=radio.rate))
    mmio = SimpleNamespace(read=lambda _: 0)
    hw = SimpleNamespace(src_regs=mmio, checked=SimpleNamespace(registers=lambda _: mmio),
                         prepare_receive=lambda: {})
    def failed():
        raise TimeoutError('DMA timed out')
    snapshots = SimpleNamespace(capture=failed, stop=lambda: quarantine)
    result = capture.scan_session(SimpleNamespace(radio=radio, hw=hw), tmp_path, 'A',
                                  [75000000], snapshots)
    assert result['status'] == 'FAIL' and 'DMA timed out' in result['error']
    assert result['buffers_quarantined'] == quarantine
    if quarantine:
        assert 'baseline_restore' not in result
    else:
        assert radio.configurations[-1][1] == 3840000
