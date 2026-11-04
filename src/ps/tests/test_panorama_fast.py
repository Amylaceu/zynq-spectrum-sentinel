"""Independent spectral normalization and complete fast-plan coverage."""
import numpy as np
import pytest
from sentinel.panorama import SAMPLE_RATE_HZ, tile_centers, welch_psd, stitch

@pytest.mark.parametrize('size', [4096, 65536, 131072])
def test_batched_welch_matches_scalar_reference(size):
    rng = np.random.default_rng(114)
    t = np.arange(size)
    iq = 300*np.exp(2j*np.pi*325*t/4096)+rng.normal(size=size)+1j*rng.normal(size=size)
    window = np.hanning(4096)
    spectra = [np.abs(np.fft.fft(iq[k:k+4096]/2048*window))**2
               for k in range(0, size-4096+1, 2048)]
    reference = np.fft.fftshift(np.mean(spectra, axis=0)/(SAMPLE_RATE_HZ*np.sum(window**2)))
    for batch in (1, 16, 32):
        _, power = welch_psd(iq, batch_segments=batch)
        np.testing.assert_allclose(power, reference, rtol=2e-14, atol=1e-24)

@pytest.mark.parametrize('group', ['A', 'D'])
def test_nine_mhz_plan_has_no_dc_or_edge_holes(group):
    f = np.fft.fftshift(np.fft.fftfreq(4096, 1/SAMPLE_RATE_HZ))
    plan = tile_centers(group, 9000000)
    _, power, count = stitch([(lo, f, np.ones(len(f))) for lo in plan], group)
    assert np.all(count > 0) and np.all(power == 1)
    assert len(plan) < len(tile_centers(group))
    with pytest.raises(ValueError):
        tile_centers(group, 18000000)
