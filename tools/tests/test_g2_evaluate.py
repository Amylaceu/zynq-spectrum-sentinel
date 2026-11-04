import copy
import importlib.util
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from g2_evaluate import evaluate


def valid():
    return (dict(status='completed', source='rf', RF_TX_requested=False, elapsed_total_s=600,
                 telemetry=[dict(display_fps=28.49)], ui=dict(version='v3', errors=0,
                 submissions=100, timing_samples_ms=[25]*100)),
            dict(status='PASS', worker_exit_code=0, stop_readback=dict(status='PASS',
                 gpio_data=0, source_ctrl=0, audio_control=0)))


def test_real_threshold_boundaries_and_no_visual_claim():
    result, execution = valid()
    value = evaluate(result, execution)
    assert value['status'] == 'PASS_METRICS_VISUAL_SEPARATE'
    assert 'separate' in value['human_readability']


@pytest.mark.parametrize('fault', ['short', 'slow', 'tail', 'fps', 'empty', 'error', 'unsafe', 'worker'])
def test_failures_are_not_hidden_by_claimed_summary(fault):
    result, execution = valid()
    if fault == 'short':
        result['elapsed_total_s'] = 599.99
    elif fault == 'slow':
        result['ui']['timing_samples_ms'] = [25.01]*100
        result['ui']['median_ms'] = 1
    elif fault == 'tail':
        result['ui']['timing_samples_ms'][-10:] = [41]*10
    elif fault == 'fps':
        result['telemetry'][0]['display_fps'] = 28.48
    elif fault == 'empty':
        result['ui']['timing_samples_ms'] = []
    elif fault == 'error':
        result['ui']['errors'] = 1
    elif fault == 'unsafe':
        execution['stop_readback']['source_ctrl'] = 1
    elif fault == 'worker':
        execution['worker_exit_code'] = 1
    assert evaluate(result, execution)['status'] == 'FAIL'
