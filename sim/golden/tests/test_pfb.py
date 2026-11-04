import numpy as np
import pytest
from scipy.signal import lfilter

from sim.golden.pfb import (
    channel_center, decimate, design_prototype, nco_mix, pfb_os2, pfb_os2_fixed, select_channel,
)


@pytest.mark.parametrize("ch", range(16))
def test_each_channel_center_suppresses_neighbours_and_becomes_dc(ch):
    h = design_prototype()
    n = np.arange(4096)
    tone = np.exp(2j * np.pi * ch * n / 16)
    y = pfb_os2(tone, h)[16:]
    powers = np.mean(np.abs(y) ** 2, axis=0)
    assert np.argmax(powers) == ch
    rejection = 10 * np.log10(powers[ch] / max(powers[(ch - 1) % 16], powers[(ch + 1) % 16]))
    assert rejection >= 60
    assert np.max(np.abs(y[:, ch] - y[0, ch])) < 1e-10
    assert abs(abs(y[0, ch]) - 1) < 1e-4


def test_commutator_matches_independent_modulated_filter_bank():
    rng = np.random.default_rng(92)
    x = rng.normal(size=1536) + 1j * rng.normal(size=1536)
    h = design_prototype() / 131072
    actual = pfb_os2(x, h)
    t = np.arange(0, len(x), 8)
    for ch in range(16):
        omega = 2 * np.pi * ch / 16
        modulated = h * np.exp(1j * omega * np.arange(len(h)))
        expected = lfilter(modulated, [1], x)[t] * np.exp(-1j * omega * t)
        np.testing.assert_allclose(actual[:, ch], expected, atol=1e-11)


@pytest.mark.parametrize("ch", [0, 3, 8, 13])
def test_fixed_channel_accuracy_and_determinism(ch):
    tone = 14000 * np.exp(2j * np.pi * ch * np.arange(2048) / 16)
    iq = np.rint(np.column_stack((tone.real, tone.imag))).astype(np.int16)
    quantized = iq[:, 0].astype(float) + 1j * iq[:, 1]
    h = design_prototype()
    fixed = pfb_os2_fixed(iq, h)
    assert fixed.shape == (256, 16, 2) and fixed.dtype == np.int16
    f = fixed[..., 0].astype(float) + 1j * fixed[..., 1].astype(float)
    reference = pfb_os2(quantized, h)
    error = np.max(np.abs(f - reference))
    print(f"PFB fixed ch={ch} max error={error:.3f} IQ LSB")
    assert error < 2
    p = np.mean(np.abs(f[16:]) ** 2, axis=0)
    assert np.argmax(p) == ch
    assert np.sqrt(max(p[(ch + 1) % 16], p[(ch - 1) % 16])) < np.sqrt(p[ch]) / 1000
    np.testing.assert_array_equal(fixed, pfb_os2_fixed(iq, h))


def test_fixed_random_data_agrees_with_float_filter_bank():
    rng = np.random.default_rng(113)
    iq = rng.integers(-14000, 14001, (2048, 2), dtype=np.int16)
    h = design_prototype()
    result = pfb_os2_fixed(iq.reshape(-1), h)
    actual = result[..., 0].astype(float) + 1j * result[..., 1].astype(float)
    expected = pfb_os2(iq[:, 0].astype(float) + 1j * iq[:, 1], h)
    assert np.max(np.abs(actual - expected)) < 2


def test_channel_selection_and_nco_residual_removal():
    fs = 30.72e6
    for ch in range(16):
        center = channel_center(ch, fs)
        f = center + 12345
        selected, residual = select_channel(f, fs)
        assert selected == ch and residual == pytest.approx(12345)
    ch, residual = select_channel(fs / 2 - 100, fs)
    assert ch == 8 and residual == pytest.approx(-100)
    fs_ch = fs / 8
    tone = np.exp(2j * np.pi * 12345 * np.arange(10000) / fs_ch)
    mixed = nco_mix(tone, 12345, fs_ch)
    assert np.max(np.abs(mixed - 1)) < 1e-5


@pytest.mark.parametrize("r", [1, 2, 4, 8])
def test_decimator_length_dc_gain_and_alias_rejection(r):
    x = np.ones(8192, dtype=np.complex128)
    y = decimate(x, r)
    assert len(y) == (len(x) + r - 1) // r
    np.testing.assert_allclose(y[200:], 1, atol=1e-12)
    if r > 1:
        tone = np.exp(2j * np.pi * 0.4 * np.arange(len(x)))
        alias = decimate(tone, r)[200:]
        assert 10 * np.log10(np.mean(np.abs(alias) ** 2)) < -60


def test_invalid_configurations_and_empty_input():
    h = design_prototype()
    assert pfb_os2(np.array([]), h).shape == (0, 16)
    assert pfb_os2_fixed(np.empty((0, 2), dtype=np.int16), h).shape == (0, 16, 2)
    with pytest.raises(ValueError):
        pfb_os2(np.ones(100), h, d=4)
    with pytest.raises(ValueError):
        select_channel(20e6, 30.72e6)
    with pytest.raises(ValueError):
        decimate(np.ones(20), 3)
