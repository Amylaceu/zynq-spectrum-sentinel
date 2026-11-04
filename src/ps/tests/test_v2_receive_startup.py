"""Startup reset may clear calibration history, never an active RX fault."""
from types import SimpleNamespace

import pytest

from src.ps.sentinel.v2 import V2


def hardware(monkeypatch, *, running=False, persistent=False, assertion_fails=False):
    monkeypatch.setattr('src.ps.sentinel.v2.time.sleep', lambda _: None)
    writes = []
    state = {'reset': 3}

    def read(offset):
        if offset == 0x5c:
            return 1
        if assertion_fails and state['reset'] == 2:
            return 3
        return state['reset']

    def write(offset, value):
        assert offset == 0x40
        writes.append(value)
        state['reset'] = value

    counts = [0]

    def snapshot():
        counts[0] += 1
        return SimpleNamespace(status=1 if counts[0] == 1 or persistent else 0)

    hw = V2.__new__(V2)
    hw.src_regs = SimpleNamespace(read=lambda _: int(running))
    hw.checked = SimpleNamespace(registers=lambda _: SimpleNamespace(read=read, write=write))
    hw.perf = SimpleNamespace(snapshot=snapshot, clear=lambda: None)
    return hw, writes


def test_calibration_history_reset_preserves_mmcm(monkeypatch):
    hw, writes = hardware(monkeypatch)
    result = hw.prepare_receive()
    assert writes == [2, 3]
    assert result['perf_before']['status'] == 1
    assert result['perf_after']['status'] == 0


def test_active_acquisition_cannot_clear_fault(monkeypatch):
    hw, writes = hardware(monkeypatch, running=True)
    with pytest.raises(RuntimeError, match='Stop source'):
        hw.prepare_receive()
    assert not writes


def test_persistent_overflow_still_aborts(monkeypatch):
    hw, writes = hardware(monkeypatch, persistent=True)
    with pytest.raises(RuntimeError, match='persists'):
        hw.prepare_receive()
    assert writes == [2, 3]


def test_assertion_failure_restores_original_reset(monkeypatch):
    hw, writes = hardware(monkeypatch, assertion_fails=True)
    with pytest.raises(RuntimeError, match='assertion failed'):
        hw.prepare_receive()
    assert writes == [2, 3]
