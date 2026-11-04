"""Tone acceptance must tolerate one bin without accepting an unrelated spur."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from accept_x2_selftest import verify_tone_peaks


def test_adjacent_bin_tones_pass():
    single = np.zeros(2048)
    triple = np.zeros(2048)
    single[1089] = 100
    triple[[723, 1089, 1324]] = [100, 90, 80]
    verify_tone_peaks(single, triple)


def test_unrelated_stronger_peak_rejected():
    single = np.zeros(2048)
    triple = np.zeros(2048)
    single[1088] = 100
    triple[[724, 1088, 1324]] = [100, 90, 80]
    triple[1800] = 1000
    with pytest.raises(ValueError, match='Three-tone'):
        verify_tone_peaks(single, triple)
