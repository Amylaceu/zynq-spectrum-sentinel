import struct

import numpy as np
import pytest

from sim.golden.cfar import TARGET_DTYPE, alpha_for_pfa, cfar, cluster, pack_targets


@pytest.mark.parametrize("mode", ["CA", "GO", "SO"])
def test_reference_windows_against_independent_integer_loop(mode):
    rng = np.random.default_rng(30)
    p = rng.integers(0, 2**32, 65, dtype=np.uint32)
    n, g, alpha = 4, 2, 1821
    thresholds, hits = cfar(p, mode, n, g, alpha, dc_mask=-1)
    for k in range(len(p)):
        l = sum(int(p[(k - g - j) % len(p)]) for j in range(1, n + 1))
        r = sum(int(p[(k + g + j) % len(p)]) for j in range(1, n + 1))
        z = (l + r) >> 3 if mode == "CA" else (max(l, r) if mode == "GO" else min(l, r)) >> 2
        t = min((z * alpha) >> 8, 2**32 - 1)
        assert thresholds[k] == t
        assert hits[k] == (int(p[k]) > t)


@pytest.mark.parametrize("mode", ["CA", "GO", "SO"])
def test_noise_false_alarm_rate(mode):
    rng = np.random.default_rng(20261102)
    p = np.rint(rng.exponential(2**20, 262144)).astype(np.uint32)
    target = 1e-3
    alpha = alpha_for_pfa(target, 16, mode)
    _, hits = cfar(p, mode, 16, 2, alpha, dc_mask=-1)
    measured = np.mean(hits)
    print(f"{mode} alpha={alpha}/256 Pfa={measured:.6g} target={target}")
    assert 0.5 <= measured / target <= 2


def test_three_targets_have_correct_boundaries():
    p = np.full(2048, 1000, dtype=np.uint32)
    bounds = [(180, 183), (650, 654), (1500, 1502)]
    for start, stop in bounds:
        p[start:stop + 1] = 1000000
    _, hit = cfar(p, alpha_q88=alpha_for_pfa(1e-3))
    targets = cluster(hit, p)
    assert len(targets) == 3
    for target, (start, stop) in zip(targets, bounds):
        assert abs(int(target["start"]) - start) <= 1
        assert abs(int(target["stop"]) - stop) <= 1


def test_dc_mask_strict_comparison_and_saturation():
    p = np.full(64, 100, dtype=np.uint32)
    _, hits = cfar(p, n=4, g=1, alpha_q88=256, dc_mask=-1)
    assert not hits.any()  # equality is not detection
    p[31:34] = 1000000
    _, hits = cfar(p, n=4, g=1, alpha_q88=0, dc_mask=1)
    assert not hits[31:34].any() and hits[30] == hits[34] == 1
    threshold, _ = cfar(np.full(64, 0xFFFFFFFF, dtype=np.uint32), n=4, alpha_q88=65535)
    assert np.all(threshold == 0xFFFFFFFF)


def test_cluster_merge_gap_peak_tie_sum_and_binary_layout():
    p = np.array([0, 10, 20, 3, 4, 20, 0, 0, 0, 100], dtype=np.uint32)
    h = np.array([0, 1, 1, 0, 0, 1, 0, 0, 0, 1], dtype=np.uint8)
    t = cluster(h, p, gap=2)
    assert t.dtype == TARGET_DTYPE and t.dtype.itemsize == 16
    assert t[0].tolist() == (1, 5, 2, 0, 20, 57)
    assert t[1].tolist() == (9, 9, 9, 0, 100, 100)
    assert pack_targets(t)[:16] == struct.pack("<HHHHII", 1, 5, 2, 0, 20, 57)


def test_cluster_overflow_and_sum_saturation():
    p = np.full(100, 0xFFFFFFFF, dtype=np.uint32)
    hit = np.zeros(100, dtype=np.uint8)
    hit[[0, 1, 30, 50, 70]] = 1
    t = cluster(hit, p, gap=0, max_targets=2)
    assert len(t) == 2 and np.all(t["flags"] == 1)
    assert t[0]["sum_pwr"] == 0xFFFFFFFF
    assert len(cluster(np.zeros(100), p)) == 0


def test_invalid_configuration_is_rejected():
    p = np.ones(64, dtype=np.uint32)
    for kwargs in ({"n": 3}, {"edge": "zero"}, {"alpha_q88": -1}, {"dc_mask": -2}):
        with pytest.raises(ValueError):
            cfar(p, **kwargs)
    with pytest.raises(ValueError):
        pack_targets(np.zeros(2, dtype=np.uint64))
