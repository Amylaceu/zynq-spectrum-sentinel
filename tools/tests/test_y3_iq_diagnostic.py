"""Independent analytic checks for the FM fault-localization tooling."""
import importlib.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('y3_iq_analysis', ROOT/'tools/analyze_y3_iq_diagnostic.py')
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def test_selected_pfb_channel_matches_polyphase_reference():
    rng = np.random.default_rng(931)
    x = rng.normal(size=8192)+1j*rng.normal(size=8192)
    taps = analysis.read_signed_hex(ROOT/'src/rtl/pfb/x5_pfb_coeff.hex', 18)
    reference = analysis.pfb_os2(x, taps)
    for channel in (-7, -1, 0, 1, 7):
        np.testing.assert_allclose(analysis.channelize(x, taps, channel),
                                   reference[:, channel % 16], atol=2e-12, rtol=1e-10)


def test_known_fm_recovers_pilot_and_residual_offset():
    fs = 480000
    t = np.arange(65536)/fs
    frequency = 10000+12000*np.sin(2*np.pi*1000*t)+7500*np.sin(2*np.pi*19000*t)
    iq = .5*np.exp(2j*np.pi*np.cumsum(frequency)/fs)
    result = analysis.discriminator_metrics(iq, 10000)
    assert abs(result['pilot_frequency_hz']-19000) < 30
    assert result['pilot_prominence_db'] > 30
    assert abs(result['discriminator_dc_hz']) < 100
    assert result['large_excursion_fraction'] == 0


def test_current_audio_math_preserves_expected_tone_gain():
    fs = 480000
    t = np.arange(131072)/fs
    frequency = -10000+20000*np.sin(2*np.pi*1000*t)
    iq = .7*np.exp(2j*np.pi*np.cumsum(frequency)/fs)
    fir = analysis.read_signed_hex(ROOT/'src/rtl/audio_y3/rom/y3_audio_fir.hex', 18)
    pcm = analysis.audio_rtl_math(iq, -10000, fir)[960:]
    expected = .2*(20000/75000)/np.sqrt(1+(2*np.pi*1000*75e-6)**2)
    assert abs(np.sqrt(2)*np.std(pcm)/expected-1) < .04
    assert abs(np.mean(pcm)) < .001
