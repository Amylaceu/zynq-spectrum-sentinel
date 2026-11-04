"""Protect supplementary-frequency metrics and counterfactual replay boundaries."""

from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyze_x1_frozen_replay import frequency_summary, replay, verify_diagnostic
from run_x1_board import sha


def target(bin_index, power=100):
    return dict(start=bin_index, stop=bin_index, peak_bin=bin_index, peak_power=power)


def test_counts_attempts_once_and_retains_missing_snapshots():
    rows = [dict(targets=[target(704), target(705, 200)]),
            dict(snapshot_available=False), dict(targets=[])]
    result = frequency_summary(rows, 96400000, 3840000, 95800000)
    assert result['attempts'] == 3
    assert result['detected_attempts'] == 1
    assert result['detection_rate_all_attempts'] == 1/3
    assert result['detected_frame_indices'] == [0]
    assert result['peak_frequency_hz_median'] == 95801875


def test_uses_actual_lo_and_keeps_two_frequency_windows_distinct():
    rows = [dict(targets=[target(518)]), dict(targets=[target(704)])]
    lower = frequency_summary(rows, 96399998, 3840000, 95450000)
    upper = frequency_summary(rows, 96399998, 3840000, 95800000)
    assert lower['detected_frame_indices'] == [0]
    assert upper['detected_frame_indices'] == [1]
    assert lower['peak_frequency_hz_median'] == 95451248


@pytest.mark.parametrize('peak_frequency,expected', [(95775000, 1), (95774999, 0),
                                                   (95825000, 1), (95825001, 0)])
def test_tolerance_edges_are_inclusive(peak_frequency, expected):
    # Bin 1024 is exactly LO, so exercise both boundaries without rounding.
    result = frequency_summary([dict(targets=[target(1024)])],
                               peak_frequency, 3840000, 95800000)
    assert result['detected_attempts'] == expected


def test_empty_attempts_rejected_and_no_detection_is_explicit():
    with pytest.raises(ValueError, match='Empty'):
        frequency_summary([], 96400000, 3840000, 95800000)
    result = frequency_summary([dict(targets=[])], 96400000, 3840000, 95800000)
    assert result['detected_attempts'] == 0
    assert result['peak_frequency_hz_range'] is None


def test_replay_exposes_width_loss_without_modifying_inputs():
    powers = np.ones((4, 2048), dtype=np.uint32)
    powers[::2, 704] = 100000  # Isolated hit: rejected by deployed width two.
    powers[1::2, 704:706] = 100000
    original = powers.copy()
    data = {'rate_hz': 3840000, 'samples': [
        {'index': index, 'actual_lo_hz': 96400000, 'actual_rate_hz': 3840000}
        for index in range(4)]}
    baseline = replay(data, powers, {})
    counterfactual = replay(data, powers, {'min_width_bins': 1})
    frequency = '95800000'
    assert baseline['summary']['all']['frequencies'][frequency]['detected_attempts'] == 2
    assert counterfactual['summary']['all']['frequencies'][frequency]['detected_attempts'] == 4
    assert baseline['model_parameters']['min_width_bins'] == 2
    assert counterfactual['summary']['early_half']['frames'] == 2
    assert np.array_equal(original, powers)


def test_hash_tampering_rejected_before_replay(tmp_path):
    path = tmp_path / 'damaged.json'
    path.write_text('{}')
    Path(str(path) + '.sha256').write_text(sha(path) + '  damaged.json\n')
    path.write_text('{"changed": true}')
    with pytest.raises(ValueError, match='hash mismatch'):
        verify_diagnostic(path)
