import numpy as np
import pytest

from sim.golden.fft_cmodel import fft_i16
from sim.golden.spectrum import (
    fft_fixed, power_u32, to_db_q88, welch_update, window_coefs,
)


def test_amd_fft_dc_scale_and_zero_bins():
    x = np.zeros((2048, 2), dtype=np.int16)
    x[:, 0] = 8192
    out = fft_i16(x)
    np.testing.assert_array_equal(out[0], [8192, 0])
    assert not np.any(out[1:])


@pytest.mark.parametrize("bin_number", [0, 137, 1023, -327])
def test_tone_natural_order_and_fixed_output(bin_number):
    n = 2048
    tone = 12000 * np.exp(2j * np.pi * bin_number * np.arange(n) / n)
    x = np.rint(np.column_stack((tone.real, tone.imag))).astype(np.int16)
    result = fft_fixed(x.reshape(-1), window_coefs())
    assert result.dtype == np.int32 and result.shape == (n, 2)
    assert not np.any(result & 255)
    p = power_u32(result)
    assert np.argmax(p) == bin_number % n
    # BH4 coherent gain is 0.35875; compare amplitude with a small LSB tolerance.
    expected = 12000 * 0.35875
    actual = np.linalg.norm(result[bin_number % n].astype(np.float64)) / 256
    assert abs(actual - expected) < 4


def test_quantized_window_sidelobes():
    w = window_coefs()
    assert w.dtype == np.int64 and w.min() >= 0 and w.max() == 131071
    assert np.all(w[1:] == w[:0:-1])
    spectrum = np.abs(np.fft.rfft(w, 2048 * 256))
    # Main lobe extends to +/-4 bins. Measure all sidelobes beyond that null.
    sidelobe = np.max(spectrum[4 * 256 + 1:])
    measured_db = 20 * np.log10(sidelobe / spectrum[0])
    print(f"quantized BH4 peak sidelobe={measured_db:.3f} dBc")
    assert measured_db < -90


def test_random_fft_against_independent_float_transform():
    rng = np.random.default_rng(102)
    x = rng.integers(-12000, 12001, (2048, 2), dtype=np.int16)
    w = window_coefs()
    actual = fft_fixed(x, w).astype(np.float64) / 256
    win_x = (x.astype(np.int64) * w[:, None]) >> 17
    expected = np.fft.fft(win_x[:, 0] + 1j * win_x[:, 1]) / 2048
    error = actual[:, 0] + 1j * actual[:, 1] - expected
    rms_error = np.sqrt(np.mean(np.abs(error) ** 2))
    print(f"AMD native16 FFT vs float RMS error={rms_error:.4f} LSB")
    # This checks normalization and ABI, not a false claim of >70 dB SQNR.
    assert rms_error < 3
    np.testing.assert_array_equal(fft_fixed(x, w), fft_fixed(x, w))


def test_rectangular_window_shift_is_arithmetic():
    x = np.zeros((2048, 2), dtype=np.int16)
    x[:, 0] = 8192
    x[:, 1] = -8192
    y = fft_fixed(x, window_coefs("rect"))
    np.testing.assert_array_equal(y[0], [8191 << 8, -8192 << 8])
    assert not np.any(y[1:])


def test_power_width_and_truncation():
    x = np.array([[1 << 23, 0], [0, 0]], dtype=np.int64)
    with pytest.raises(ValueError):
        power_u32(x)
    x[0] = [-(1 << 23), -(1 << 23)]
    np.testing.assert_array_equal(power_u32(x), np.array([1 << 31, 0], dtype=np.uint32))
    x[0] = [257, 511]
    assert power_u32(x)[0] == (257**2 + 511**2) >> 16


def test_welch_decreasing_unsigned_values():
    prev = np.array([0xFFFFFFFF, 100, 0, 8], dtype=np.uint32)
    new = np.array([0, 101, 0xFFFFFFFF, 0], dtype=np.uint32)
    expected = [int(a) + ((int(b) - int(a)) >> 3) for a, b in zip(prev, new)]
    np.testing.assert_array_equal(welch_update(prev, new, 3), expected)
    np.testing.assert_array_equal(welch_update(prev, new, 0), new)


def test_db_lut_error_across_entire_dynamic_range():
    rng = np.random.default_rng(222)
    powers = np.unique(np.r_[
        np.arange(1, 65537, dtype=np.uint64),
        rng.integers(1, 2**32, 300000, dtype=np.uint64),
        np.array([2**i + j for i in range(1, 32) for j in (-1, 0, 1)], dtype=np.uint64),
        np.array([2**32 - 1], dtype=np.uint64),
    ])
    error = np.max(np.abs(to_db_q88(powers).astype(np.float64) / 256 - 10 * np.log10(powers)))
    print(f"Q8.8 log LUT maximum error={error:.5f} dB")
    assert error < 0.05
    assert to_db_q88(np.uint32(0)) == -32768
    assert to_db_q88(np.uint32(1)) == 0


def test_invalid_numeric_inputs():
    with pytest.raises(ValueError):
        fft_fixed(np.zeros(16, dtype=np.int16), np.zeros(7, dtype=np.int64))
    with pytest.raises(ValueError):
        fft_i16(np.zeros((12, 2), dtype=np.int16))
    with pytest.raises(ValueError):
        to_db_q88(np.array([-1]))
    with pytest.raises(ValueError):
        welch_update(np.array([1]), np.array([0]), -1)
