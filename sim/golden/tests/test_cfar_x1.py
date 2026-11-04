"""Independent scalar oracle and boundary cases for X1 clustering."""
import struct

import numpy as np
import pytest

from sim.golden.cfar import TARGET_DTYPE, cfar, cluster, pack_targets
from sim.golden.cfar_x1 import cluster_x1, detect_x1, mask_bins


def scalar_oracle(hit, power, width, gap, masks, limit=32):
    """Literal scan of bins with Python ints; no production grouping/sorting API."""
    ranges = []
    first = last = None
    for index, bit in enumerate(hit):
        blocked = any(a <= index <= b for a, b in masks)
        if blocked or (last is not None and index - last - 1 > gap):
            if first is not None:
                ranges.append((first, last))
            first = last = None
        if bit and not blocked:
            if first is None:
                first = index
            last = index
    if first is not None:
        ranges.append((first, last))
    rows = []
    for start, stop in ranges:
        if stop - start + 1 < width:
            continue
        peak = start
        total = 0
        for index in range(start, stop + 1):
            total = min(0xffffffff, total + int(power[index]))
            if int(power[index]) > int(power[peak]):
                peak = index
        rows.append((start, stop, peak, 0, int(power[peak]), total))
    candidate_count = len(rows)
    selected = []
    while rows and len(selected) < limit:
        best = 0
        for index in range(1, len(rows)):
            if rows[index][4] > rows[best][4] or (
                rows[index][4] == rows[best][4] and rows[index][0] < rows[best][0]
            ):
                best = index
        row = rows.pop(best)
        selected.append((*row[:3], int(candidate_count > limit), *row[4:]))
    return selected, len(ranges), candidate_count


def test_retains_strongest_32_including_last_bin_and_reports_overflow():
    power = np.zeros(2048, dtype=np.uint32)
    locations = list(range(0, 128, 4)) + [2047]
    power[locations] = np.arange(1, 34, dtype=np.uint32)
    result = cluster_x1(power > 0, power, min_width_bins=0, merge_gap_bins=0)
    assert result.candidate_count == result.raw_count == 33
    assert result.overflow and result.status_latch == 16
    assert list(result.targets['start']) == locations[:0:-1]
    assert np.all(result.targets['flags'] == 1)
    assert result.targets[0]['stop'] == 2047


def test_equal_power_order_is_start_ascending_with_exactly_32_candidates():
    power = np.zeros(128, dtype=np.uint32)
    power[::4] = 100
    result = cluster_x1(power > 0, power, 1, 0)
    assert list(result.targets['start']) == list(range(0, 128, 4))
    assert not result.overflow and result.status_latch == 0
    assert np.all(result.targets['flags'] == 0)


@pytest.mark.parametrize('width, expected', [(0, 3), (1, 3), (2, 2), (3, 1), (2048, 0)])
def test_inclusive_width_filter_before_capacity_count(width, expected):
    power = np.zeros(40, dtype=np.uint32)
    power[2] = 10
    power[10:12] = 20
    power[37:40] = 30
    result = cluster_x1(power > 0, power, width, 0)
    assert result.raw_count == 3 and result.candidate_count == expected
    assert result.filtered_count == 3 - expected
    assert not result.overflow


def test_merge_gap_boundary_and_higher_nonhit_peak_are_preserved():
    power = np.zeros(40, dtype=np.uint32)
    hit = np.zeros(40, dtype=np.uint8)
    hit[[2, 9, 17]] = 1
    power[[2, 9, 17]] = 10
    power[5] = 90
    result = cluster_x1(hit, power, 1, 6)
    assert result.targets[0].tolist() == (2, 9, 5, 0, 90, 110)
    assert result.targets[1].tolist() == (17, 17, 17, 0, 10, 10)
    assert pack_targets(result.targets)[:16] == struct.pack('<HHHHII', 2, 9, 5, 0, 90, 110)


def test_masks_split_small_gaps_and_exclude_masked_power():
    power = np.ones(24, dtype=np.uint32)
    power[10] = 0xffffffff
    hit = np.zeros(24, dtype=np.uint8)
    hit[[8, 9, 10, 11, 12]] = 1
    result = cluster_x1(hit, power, 2, 255, mask_table=[(10, 10)])
    assert result.hit_count == 4 and result.candidate_count == 2
    assert [(int(t['start']), int(t['stop'])) for t in result.targets] == [(8, 9), (11, 12)]
    assert np.all(result.targets['sum_pwr'] == 2)


def test_dc_mask_is_hard_boundary_and_does_not_change_thresholds():
    power = np.ones(64, dtype=np.uint32)
    power[29:36] = 100000
    threshold, hit, result = detect_x1(power, n=4, g=1, alpha_q88=0,
                                      dc_mask=1, min_width_bins=1, merge_gap_bins=6)
    original_threshold, _ = cfar(power, n=4, g=1, alpha_q88=0, dc_mask=-1)
    assert np.array_equal(threshold, original_threshold)
    assert not hit[31:34].any()
    assert result.candidate_count == 2
    assert all(int(t['stop']) < 31 or int(t['start']) > 33 for t in result.targets)


def test_explicit_masks_leave_reference_noise_estimate_unchanged():
    power = np.arange(1, 65, dtype=np.uint32) ** 3
    expected, _ = cfar(power, n=4, g=1, dc_mask=-1)
    actual, hit, _ = detect_x1(power, n=4, g=1, dc_mask=-1, mask_table=[(0, 15)])
    assert np.array_equal(actual, expected)
    assert not hit[:16].any()


def test_mask_union_capacity_edges_empty_and_saturated_sum():
    table = [(i, i) for i in range(16)]
    table[3] = (2, 4)
    mask = mask_bins(32, list(reversed(table)))
    assert mask[:16].all() and not mask[16:].any()
    power = np.full(64, 0xffffffff, dtype=np.uint32)
    result = cluster_x1(np.ones(64), power)
    assert result.targets[0]['sum_pwr'] == 0xffffffff
    empty = cluster_x1(np.zeros(64), power)
    assert empty.targets.dtype == TARGET_DTYPE and len(empty.targets) == 0
    assert empty.candidate_count == empty.raw_count == empty.hit_count == 0


@pytest.mark.parametrize('kwargs', [
    {'min_width_bins': -1}, {'min_width_bins': 2049}, {'min_width_bins': True},
    {'merge_gap_bins': 256}, {'merge_gap_bins': 1.5}, {'max_targets': 33},
    {'mask_table': [(0, 0)] * 17}, {'mask_table': [(4, 3)]},
    {'mask_table': [(-1, 2)]}, {'mask_table': [(0, 64)]},
    {'mask_table': [(0,)]}, {'dc_mask': 255},
])
def test_invalid_hardware_configuration_rejected(kwargs):
    with pytest.raises(ValueError):
        cluster_x1(np.zeros(64), np.ones(64, dtype=np.uint32), **kwargs)


def test_random_frames_match_independent_scalar_oracle():
    rng = np.random.default_rng(20261103)
    for _ in range(100):
        power = rng.integers(0, 2**32, 256, dtype=np.uint32)
        hit = (rng.random(256) < .22).astype(np.uint8)
        width, gap = int(rng.integers(0, 6)), int(rng.integers(0, 9))
        starts = rng.integers(0, 250, 4)
        masks = [(int(s), int(s) + int(rng.integers(0, 5))) for s in starts]
        result = cluster_x1(hit, power, width, gap, masks)
        rows, raw_count, candidates = scalar_oracle(hit, power, width, gap, masks)
        assert result.targets.tolist() == rows
        assert result.raw_count == raw_count and result.candidate_count == candidates
        assert result.filtered_count == raw_count - candidates
        assert result.overflow == (candidates > 32)


def test_v1_default_behavior_is_unchanged():
    power = np.zeros(128, dtype=np.uint32)
    power[::4] = np.arange(1, 33)
    old = cluster(power > 0, power, gap=0)
    assert list(old['start']) == list(range(0, 128, 4))
    assert old[0]['peak_pwr'] == 1
