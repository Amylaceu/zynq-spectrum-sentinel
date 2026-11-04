import numpy as np
import pytest
from src.ps.sentinel.rx_acceptance import analyze_bist_tone


def tone():
    z = 512*np.exp(2j*np.pi*np.arange(4096)/32)
    return np.rint(np.column_stack([z.real,z.imag,z.real,-z.imag])).astype('<i2')


def test_four_channel_order_and_both_frequency_signs():
    result = analyze_bist_tone(tone(),30720000)
    assert result['passed']
    assert [c['peak_hz'] for c in result['channels']] == [960000.,-960000.]


@pytest.mark.parametrize('damage', ['zero','no_q','wrong_frequency','noise'])
def test_rejects_non_tone_and_bad_quadrature(damage):
    data = tone()
    if damage == 'zero': data[:] = 0
    if damage == 'no_q': data[:,1::2] = 0
    if damage == 'wrong_frequency': data = data[np.arange(len(data))*2 % len(data)]
    if damage == 'noise': data = np.random.default_rng(5).integers(-1000,1000,data.shape,dtype=np.int16)
    assert not analyze_bist_tone(data,30720000)['passed']
