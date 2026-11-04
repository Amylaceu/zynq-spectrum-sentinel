"""Prevent incomplete/error-bearing acquisitions from becoming PASS evidence."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools'))
from analyze_x3 import analyze_digital, analyze_receive, checked


@pytest.fixture
def digital():
    return json.loads((ROOT/'board/measurements/x3_perf_r3.json').read_text())


def test_complete_digital_has_failed_original_latency(digital):
    result = analyze_digital(digital)
    assert result['count'] == 1000
    assert result['latency_under_200us'] == 'FAIL'
    assert 1870 < result['post_welch_frames_per_s_avg0'] < 1880


@pytest.mark.parametrize('fault', ['missing', 'duplicate', 'counter', 'golden', 'error'])
def test_corrupt_or_partial_digital_is_rejected(digital, fault):
    data = deepcopy(digital)
    if fault == 'missing':
        data['latency']['samples'].pop()
    elif fault == 'duplicate':
        data['latency']['samples'][1] = data['latency']['samples'][0]
    elif fault == 'counter':
        data['latency']['samples'][42]['after']['samples'] += 1
    elif fault == 'golden':
        data['cpu']['detector_fixture']['threshold'][12] ^= 1
    else:
        data['digital_throughput']['after']['status'] |= 1
    with pytest.raises(ValueError):
        analyze_digital(data)


def test_first_failed_receive_cannot_be_promoted_to_pass(digital):
    with pytest.raises(ValueError):
        analyze_receive(digital)


def test_receive_zero_baseline_and_safety_required():
    data = json.loads((ROOT/'board/measurements/x3_receive_r2.json').read_text())
    assert analyze_receive(data)['status'] == 'PASS_30S_WINDOW'
    data['receive']['samples'][2]['perf']['status'] |= 1
    with pytest.raises(ValueError):
        analyze_receive(data)


def test_digest_detects_replaced_evidence(tmp_path):
    path = tmp_path/'measurement.json'
    path.write_text('{"status":"PASS"}')
    Path(str(path)+'.sha256').write_text('0'*64+'  measurement.json\n')
    with pytest.raises(ValueError, match='digest'):
        checked(path)
