import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pytest
from sentinel.f3_signal import cw_words, tone_metrics
from sentinel.rf.f3 import attenuation_steps, F3Radio


def test_cw_native_format_and_unused_tx2():
    words = cw_words()
    assert words.dtype == np.dtype('<i2') and words.shape == (16384, 4)
    assert not words[:, 2:].any()
    assert np.all(words % 16 == 0) and abs(words.astype(int)).max() <= 8192
    x = words[:, 0].astype(float)+1j*words[:, 1]
    m = tone_metrics(x)
    assert m['peak_hz'] == 240000 and m['cw_ratio_db'] > 50


def test_cw_ratio_accounts_for_wideband_noise():
    rng = np.random.default_rng(120)
    n = 32768
    x = 100*np.exp(2j*np.pi*240000*np.arange(n)/3840000)
    x += rng.normal(0, 10, n)+1j*rng.normal(0, 10, n)
    m = tone_metrics(x)
    assert 19 < m['cw_ratio_db'] < 23


@pytest.mark.parametrize('floor', [39, 90, float('nan'), 40.1])
def test_invalid_floor(floor):
    with pytest.raises(ValueError):
        attenuation_steps(floor)


def test_steps_start_high_end_exact_floor():
    values = attenuation_steps()
    assert values[0] == 89 and values[-1] == 40
    assert all(0 < a-b <= 3 for a, b in zip(values, values[1:]))


class NoIO:
    def __getattr__(self, name):
        raise AssertionError('Unexpected hardware access '+name)


@pytest.mark.parametrize('value', [39.75, 90, float('nan'), 40.1, True])
def test_invalid_attenuation_fails_before_io(value):
    radio = F3Radio(backend=NoIO())
    with pytest.raises(ValueError):
        radio.set_attenuation(value)


def test_wrong_lo_fails_before_io():
    with pytest.raises(ValueError):
        F3Radio(backend=NoIO()).open(lo=433920000)
