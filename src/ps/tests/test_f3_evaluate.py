"""Noise accounting and metric integrity, no hardware or inference cost."""
import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sentinel.f3_evaluate import add_noise, confusion, scores


def test_noise_power_and_determinism():
    x = np.ones((3, 4096), dtype=complex)*(.1+.2j)
    a = add_noise(x, 10, np.random.default_rng(1))
    b = add_noise(x, 10, np.random.default_rng(1))
    np.testing.assert_array_equal(a, b)
    np.testing.assert_allclose(np.mean(abs(a-x)**2, axis=1), .005, rtol=1e-6)
    np.testing.assert_array_equal(x, np.full_like(x, .1+.2j))


def test_family_merging_keeps_fine_errors():
    result = scores(np.arange(10), np.array([0, 2, 1, 4, 3, 5, 6, 7, 8, 9]))
    assert result['accuracy_10'] == .6
    assert result['accuracy_8'] == 1


@pytest.mark.parametrize('x,snr', [(np.zeros((2, 8)), 0), (np.ones(8), 0),
                                  (np.ones((1, 8)), float('nan'))])
def test_invalid_noise_input(x, snr):
    with pytest.raises(ValueError):
        add_noise(x, snr, np.random.default_rng(1))


def test_confusion_rejects_out_of_contract():
    with pytest.raises(ValueError):
        confusion([0], [10], 10)
