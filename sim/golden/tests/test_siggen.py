import numpy as np
import pytest
from scipy.signal import convolve

from sim.golden.params import MOD_CLASSES
from sim.golden.siggen import (
    gen_mod, gen_wideband, rrc_taps, to_int16_iq, from_int16_iq,
    lfsr_gauss_fixed, add_noise_fixed, noise_amp_for_snr,
)


@pytest.mark.parametrize("mod", MOD_CLASSES)
def test_unit_power_and_seeded_waveform(mod):
    x = gen_mod(mod, 4096, 8, seed=2026)
    assert x.shape == (4096,) and x.dtype == np.complex64
    assert abs(10 * np.log10(np.mean(abs(x) ** 2))) < 0.1
    np.testing.assert_array_equal(x, gen_mod(mod, 4096, 8, seed=2026))


def test_qpsk_ideal_rrc_receiver_evm():
    sps = 8
    x = gen_mod("QPSK", 65536, sps, seed=4)
    # Approximate the ideal receive RRC with 32 symbols; the TX still spans 8.
    # Truncating both TX and RX to 8 symbols doubles the finite-pulse tail error.
    rx = convolve(x, rrc_taps(sps, span=32), mode="same")[32 * sps:-32 * sps:sps]
    # Scalar gain removes only the known TX normalization/matched-filter gain.
    rx /= np.sqrt(np.mean(abs(rx) ** 2))
    ideal = (np.sign(rx.real) + 1j * np.sign(rx.imag)) / np.sqrt(2)
    evm = np.sqrt(np.mean(abs(rx - ideal) ** 2))
    assert evm < 0.01, evm


def test_adc_roundtrip_snr_and_alignment():
    x = gen_mod("16QAM", 65536, 8, seed=8)
    words = to_int16_iq(x, backoff_db=12)
    assert words.dtype == np.int16
    assert np.all((words.astype(np.int32) & 15) == 0)
    decoded = from_int16_iq(words)
    expected = x * 10 ** (-12 / 20)
    sqnr = 10 * np.log10(np.mean(abs(expected) ** 2) / np.mean(abs(decoded - expected) ** 2))
    assert sqnr > 60, sqnr


def test_adc_saturation_and_invalid_word_layout():
    np.testing.assert_array_equal(to_int16_iq(np.array([4 - 4j]), 0), [32752, -32768])
    with pytest.raises(ValueError):
        from_int16_iq(np.zeros(3, dtype=np.int16))


def test_cfo_and_iq_channel_invariants():
    a = gen_mod("QPSK", 8192, 8, fs=1e6, seed=10)
    b = gen_mod("QPSK", 8192, 8, fs=1e6, cfo_hz=32000, phase=0.7, seed=10)
    np.testing.assert_allclose(abs(a), abs(b), atol=2e-7)
    c = gen_mod("QPSK", 8192, 8, iq_imb_db=1, iq_imb_deg=5, multipath=[(0, 1), (3, 0.3j)], seed=10)
    assert np.isfinite(c).all() and abs(np.mean(abs(c) ** 2) - 1) < 1e-6


def test_inband_snr_conversion():
    n, sps, snr = 262144, 8, 15
    clean = gen_mod("QPSK", n, sps, seed=9)
    noisy = gen_mod("QPSK", n, sps, snr_db=snr, seed=9)
    measured_full = np.mean(abs(noisy - clean) ** 2)
    inband_noise = measured_full * (1 + 0.35) / sps
    measured_snr = 10 * np.log10(np.mean(abs(clean) ** 2) / inband_noise)
    assert abs(measured_snr - snr) < 0.1


def test_wideband_noise_and_reproducibility():
    config = [dict(mod="QPSK", sps=8, f_off=100000, power_dbfs=-12)]
    a = gen_wideband(config, 16384, 1e6, -70, 11)
    np.testing.assert_array_equal(a, gen_wideband(config, 16384, 1e6, -70, 11))
    assert abs(10 * np.log10(np.mean(abs(a) ** 2)) + 12) < 0.1


def test_fixed_noise_statistics_gain_saturation_and_seeds():
    seeds = (0x13579BDF, 0x2468ACE1)
    noise = lfsr_gauss_fixed(32768, *seeds)
    lanes = noise.reshape(-1, 2).astype(float)
    assert np.max(abs(lanes.mean(axis=0))) < 100
    np.testing.assert_allclose(lanes.var(axis=0), 2**24 - 1, rtol=0.07)
    assert abs(np.corrcoef(lanes.T)[0, 1]) < 0.03
    np.testing.assert_array_equal(noise[:32], lfsr_gauss_fixed(16, *seeds))
    words = np.tile(np.array([32000, -32000], dtype=np.int16), 32768)
    np.testing.assert_array_equal(add_noise_fixed(words, 0, *seeds), words)
    out = add_noise_fixed(words, 65535, *seeds)
    assert np.any(out == 32767) and np.any(out == -32768)
    assert out.dtype == np.int16
    with pytest.raises(ValueError):
        lfsr_gauss_fixed(8, 0, seeds[1])
    with pytest.raises(ValueError):
        add_noise_fixed(words, 65536, *seeds)


def test_noise_amplitude_snr_units_and_range():
    power = 1e6
    amp = noise_amp_for_snr(power, 10, 1e6, 8e6)
    full_power = 2 * (2**24 - 1) * (amp / 32768) ** 2
    actual = 10 * np.log10(power / (full_power / 8))
    assert abs(actual - 10) < 0.01
    with pytest.raises(ValueError, match="range"):
        noise_amp_for_snr(1e9, -10, 1e6, 8e6)
