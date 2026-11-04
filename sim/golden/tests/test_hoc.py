import itertools
import math

import numpy as np
import pytest

from sim.golden.hoc import (
    MOMENTS, cumulants, features_from_moments, hoc_features, moments_fixed, recommended_norm_shift,
)


def constellations():
    bpsk = np.array([-1, 1], dtype=complex)
    qpsk = np.array([1 + 1j, 1 - 1j, -1 + 1j, -1 - 1j]) / np.sqrt(2)
    qam = np.array([a + 1j * b for a in (-3, -1, 1, 3) for b in (-3, -1, 1, 3)]) / np.sqrt(10)
    return bpsk, qpsk, qam


@pytest.mark.parametrize("index,theory", [(0, 2), (1, 1), (2, 0.68)])
def test_ideal_constellation_fourth_cumulant(index, theory):
    x = np.tile(constellations()[index], 4096)
    features = hoc_features(x)
    assert features.shape == (8,) and features.dtype == np.float32
    assert abs(features[1] - theory) < 0.05
    # The same theoretical test through the integer accumulator path.
    # The hardware capture is 1024 samples; long captures require a different
    # normalization and need not retain the same finite-word feature precision.
    captured = np.resize(constellations()[index], 1024)
    q = np.rint(np.column_stack((captured.real, captured.imag)) * 12000).astype(np.int16)
    raw = moments_fixed(q, recommended_norm_shift(len(q)))
    assert not raw["overflow"]
    assert abs(features_from_moments(raw)[1] - theory) < 0.05


def partitions(items):
    if not items:
        yield []
        return
    first, *rest = items
    for p in partitions(rest):
        yield [[first]] + p
        for i in range(len(p)):
            yield p[:i] + [[first] + p[i]] + p[i + 1:]


def test_sixth_order_formulas_against_joint_partition_definition():
    # This independent combinatorial definition catches coefficient/sign errors.
    rng = np.random.default_rng(197)
    x = rng.normal(size=5000) + 0.3j * rng.normal(size=5000)
    x = np.r_[x, -x]  # all odd moments exactly zero
    m = {f"M{p}{q}": np.mean(x ** (p - q) * x.conj() ** q) for p, q in MOMENTS}
    c = cumulants(m)
    for q in range(4):
        terms = [x] * (6 - q) + [x.conj()] * q
        reference = 0j
        for blocks in partitions(list(range(6))):
            product = 1
            for block in blocks:
                product *= np.mean(np.prod([terms[i] for i in block], axis=0))
            reference += (-1) ** (len(blocks) - 1) * math.factorial(len(blocks) - 1) * product
        assert c[f"C6{q}"] == pytest.approx(reference, abs=1e-10)


def test_exact_accumulators_wrap_and_scale_metadata():
    iq = np.array([[4, 8], [-12, 4], [8, -4]], dtype=np.int16)
    result = moments_fixed(iq, 1)
    z = (iq[:, 0].astype(float) + 1j * iq[:, 1]) / 2
    for p, q in MOMENTS:
        expected = np.sum(z ** (p - q) * z.conj() ** q)
        assert result[f"M{p}{q}"] == (int(expected.real), int(expected.imag))
    unsafe = moments_fixed(np.full((1024, 2), 32767, dtype=np.int16), 0)
    assert unsafe["overflow"]
    assert all(-(1 << 47) <= lane < 1 << 47 for p, q in MOMENTS for lane in unsafe[f"M{p}{q}"])
    with pytest.raises(OverflowError):
        features_from_moments(unsafe)


def test_phase_gain_invariance_and_zero_power():
    x = np.tile(constellations()[2], 100)
    np.testing.assert_allclose(hoc_features(x), hoc_features(0.3 * np.exp(0.7j) * x), atol=1e-6)
    np.testing.assert_array_equal(hoc_features(np.zeros(100, dtype=complex)), np.zeros(8))
    assert recommended_norm_shift(1024) == 10


def test_recommended_bound_prevents_full_scale_complex_overflow():
    x = np.array(list(itertools.product([-32768, 32767], repeat=2)) * 256, dtype=np.int16)
    assert not moments_fixed(x, recommended_norm_shift(len(x)))["overflow"]
