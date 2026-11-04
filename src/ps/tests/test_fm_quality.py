import numpy as np
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sentinel.fm_quality import StereoQualityGate, stereo_quality


def test_clean_stereo_fm_passes_and_noise_fails():
    fs = 480000
    t = np.arange(4096)/fs
    frequency = -14000+16000*np.sin(2*np.pi*1000*t)+7500*np.sin(2*np.pi*19000*t)
    iq = .2*np.exp(2j*np.pi*np.cumsum(frequency)/fs)
    assert stereo_quality(iq)['good']
    rng = np.random.default_rng(941)
    noise = .1*(rng.normal(size=4096)+1j*rng.normal(size=4096))
    assert not stereo_quality(noise)['good']
    assert not stereo_quality(np.ones(4096, dtype=complex)*.1)['good']
    assert not stereo_quality(np.zeros(4096, dtype=complex))['good']


def test_gate_requires_repeated_evidence_and_recovers():
    gate = StereoQualityGate()
    assert [gate.update({'good': v}) for v in
            (True, True, False, True, True, True, False, False, True, True, True)] == [
                False, False, False, False, False, True, True, False, False, False, True]


def test_reject_invalid_samples():
    with pytest.raises(ValueError):
        stereo_quality(np.zeros(4095))
    with pytest.raises(ValueError):
        stereo_quality(np.full(4096, np.nan))
