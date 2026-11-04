"""Reject loss, torn snapshots and reset counters before accepting X2 metrics."""
from dataclasses import replace

import pytest

from src.ps.sentinel.drivers.stream_x2 import StreamSnapshot, StreamStatistics, VERSION_VALUE
from src.ps.sentinel.regs import stream_x2 as R


class Registers:
    def __init__(self, ack=0, complete=True, concurrent=False):
        self.data = {R.VERSION: VERSION_VALUE, R.SNAP_ACK: ack, R.SNAP_TOKEN: ack,
                     R.FRAMES_IN: 40, R.FRAMES_OUT: 12, R.FRAME_DROP: 28}
        self.complete, self.concurrent = complete, concurrent

    def write(self, offset, value):
        self.data[offset] = value
        if offset == R.SNAP_TOKEN and self.complete:
            self.data[R.SNAP_ACK] = value

    def read(self, offset):
        value = self.data.get(offset, 0)
        if offset == R.FRAME_DROP and self.concurrent:
            self.data[R.SNAP_ACK] += 1
        return value


def test_snapshot_token_wrap_and_conservation():
    snap = StreamStatistics(Registers(ack=0xffffffff)).snapshot()
    assert snap.token == 0
    assert snap.frames_in == 40
    snap.require_lossless()


def test_snapshot_timeout_and_concurrent_writer():
    with pytest.raises(TimeoutError):
        StreamStatistics(Registers(complete=False)).snapshot(timeout=0)
    with pytest.raises(RuntimeError, match='Concurrent'):
        StreamStatistics(Registers(concurrent=True)).snapshot()


@pytest.mark.parametrize('changes', [dict(sample_drop=1), dict(status=1), dict(status=2),
    dict(status=4), dict(frame_drop=0xffffffff), dict(frames_in=0xffffffff),
    dict(frames_in=1, frames_out=2), dict(fifo_level=4097)])
def test_invalid_metrics_rejected(changes):
    snap = StreamSnapshot(0, 0, 10, 9, 0, 0, 1)
    with pytest.raises(RuntimeError):
        replace(snap, **changes).require_lossless()


def test_counter_reset_rejected_even_without_sample_loss():
    previous = StreamSnapshot(0, 2, 10, 7, 0, 0, 1)
    current = StreamSnapshot(0, 0, 0, 0, 0, 0, 2)
    with pytest.raises(RuntimeError, match='reset/decrease'):
        current.require_monotonic(previous)


def test_stream_version_mismatch():
    registers = Registers()
    registers.data[R.VERSION] = 0x58320002
    with pytest.raises(ValueError, match='version'):
        StreamStatistics(registers)
