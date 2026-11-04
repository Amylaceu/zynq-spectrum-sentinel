import struct

import numpy as np
import pytest

from src.ps.sentinel.drivers.cfar_x1 import CfarX1
from src.ps.sentinel.drivers.regs import cfar_x1 as R


class MMIO:
    def __init__(self):
        self.values = {R.VERSION: R.VERSION_VALUE, R.FRAME_COUNT: 8,
                       R.TARGET_COUNT: 2, R.CANDIDATE_COUNT: 2, R.RAW_COUNT: 3,
                       R.FILTERED_COUNT: 1, R.HIT_COUNT: 7, R.STATUS_LATCH: 0}
        self.writes = []
        self.reads = []
        self.set_records([(30, 34, 32, 0, 100, 200), (10, 12, 10, 0, 50, 100)])

    def set_records(self, rows):
        for i, row in enumerate(rows):
            data = struct.pack('<HHHHII', *row)
            for lane in range(4):
                self.values[R.TARGETS + i * 16 + lane * 4] = struct.unpack_from('<I', data, lane * 4)[0]

    def read(self, offset):
        self.reads.append(offset)
        return self.values.get(offset, 0)

    def write(self, offset, value):
        self.writes.append((offset, value))
        self.values[offset] = value


def test_configuration_is_disabled_until_all_masks_and_parameters_are_written():
    m = MMIO()
    CfarX1(m).configure(mask_table=[(0, 3), (1022, 1026)], dc_mask=-1)
    assert m.writes[0] == (R.CTRL, 0) and m.writes[-1] == (R.CTRL, 1)
    assert m.values[R.MIN_WIDTH] == 2 and m.values[R.MERGE_GAP] == 6
    assert m.values[R.DC_MASK] == 255 and m.values[R.MASK_COUNT] == 2
    assert m.values[R.MASK] == (3 << 16)
    assert m.values[R.MASK + 4] == (1022 | (1026 << 16))
    assert all(m.values[R.MASK + i * 4] == 0 for i in range(2, 16))


@pytest.mark.parametrize('kwargs', [
    {'n': 3}, {'n': True}, {'guard': 32}, {'alpha': 65536},
    {'dc_mask': 255}, {'min_width_bins': -1}, {'min_width_bins': 2049},
    {'merge_gap_bins': 256}, {'mask_table': [(0, 2048)]},
    {'mask_table': [(4, 3)]}, {'mask_table': [(0, 0)] * 17},
])
def test_invalid_configuration_does_not_write(kwargs):
    m = MMIO()
    with pytest.raises(ValueError):
        CfarX1(m).configure(**kwargs)
    assert not m.writes


@pytest.mark.parametrize('status', [1, 2, 3])
def test_busy_or_occupancy_clearing_does_not_write(status):
    m = MMIO()
    m.values[R.STATUS] = status
    with pytest.raises(RuntimeError):
        CfarX1(m).configure()
    assert not m.writes


def test_v1_version_is_rejected_without_register_writes():
    m = MMIO()
    m.values[R.VERSION] = 0x43460001
    with pytest.raises(ValueError, match='version mismatch'):
        CfarX1(m)
    assert m.reads == [R.VERSION] and not m.writes


@pytest.mark.parametrize('mapped', [False, True])
def test_snapshot_uses_latched_status_and_one_frame_for_all_fields(mapped):
    m = MMIO()
    m.values[R.STATUS] = 16  # Different live state must not contaminate snapshot.
    if mapped:
        m.array = np.zeros(4096, dtype=np.uint32)
        for offset, value in m.values.items():
            m.array[offset // 4] = value
    result = CfarX1(m).snapshot()
    assert result.sequence == 8 and result.candidate_count == 2
    assert result.raw_count == 3 and result.filtered_count == 1
    assert not result.list_overflow and R.STATUS not in m.reads
    assert [t.peak_power for t in result.targets] == [100, 50]


def test_retries_entire_snapshot_when_frame_changes_during_metadata_read():
    class Racing(MMIO):
        def read(self, offset):
            value = super().read(offset)
            if offset == R.HIT_COUNT and self.values[R.FRAME_COUNT] == 8:
                self.values.update({R.FRAME_COUNT: 9, R.RAW_COUNT: 2,
                                    R.FILTERED_COUNT: 0, R.HIT_COUNT: 6})
            return value
    m = Racing()
    result = CfarX1(m).snapshot()
    assert result.sequence == 9 and result.hit_count == 6 and result.filtered_count == 0
    assert m.reads.count(R.FRAME_COUNT) == 4


def test_continuous_publication_is_bounded_and_never_returns_mixed_frame():
    class Racing(MMIO):
        def read(self, offset):
            if offset == R.FRAME_COUNT:
                self.values[offset] += 1
            return super().read(offset)
    m = Racing()
    with pytest.raises(RuntimeError, match='changed during read'):
        CfarX1(m).snapshot(retries=3)
    assert m.reads.count(R.FRAME_COUNT) == 6


@pytest.mark.parametrize('offset,value', [
    (R.TARGET_COUNT, 33), (R.CANDIDATE_COUNT, 33), (R.FILTERED_COUNT, 0),
    (R.STATUS_LATCH, 16), (R.HIT_COUNT, 2049), (R.STATUS_LATCH, 1),
])
def test_rejects_corrupt_same_frame_metadata(offset, value):
    m = MMIO()
    m.values[offset] = value
    with pytest.raises(ValueError):
        CfarX1(m).snapshot()


def test_rejects_unsorted_and_inconsistent_target_records():
    m = MMIO()
    m.set_records([(10, 12, 10, 0, 50, 100), (30, 34, 32, 0, 100, 200)])
    with pytest.raises(ValueError, match='sorted'):
        CfarX1(m).snapshot()
    m.set_records([(30, 34, 32, 1, 100, 200), (10, 12, 10, 0, 50, 100)])
    with pytest.raises(ValueError, match='record'):
        CfarX1(m).snapshot()


def test_capacity_overflow_is_retained_in_latch_and_every_record():
    m = MMIO()
    m.values.update({R.TARGET_COUNT: 32, R.CANDIDATE_COUNT: 33,
                     R.RAW_COUNT: 33, R.FILTERED_COUNT: 0,
                     R.HIT_COUNT: 66, R.STATUS_LATCH: 16})
    m.set_records([(i * 4, i * 4 + 1, i * 4, 1, 100 - i, 200 - i) for i in range(32)])
    result = CfarX1(m).snapshot()
    assert result.list_overflow and len(result.targets) == 32
    assert result.candidate_count == 33 and all(t.flags == 1 for t in result.targets)


def test_finite_selftest_compatibility_returns_coherent_targets():
    driver=CfarX1(MMIO())
    sequence,targets=driver.targets()
    assert sequence==8 and len(targets)==2
    assert targets[0].peak_power==100
