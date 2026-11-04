"""Evidence corruption and stale pipelines must not pass bandwidth acceptance."""
from copy import deepcopy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyze_x2 import evaluate


def measurement():
    def stream(i):
        return dict(sample_drop=0, frame_drop=i, frames_in=10*i,
                    frames_out=9*i, status=0, fifo_level=0, token=i)
    return dict(status='completed', requested_rate_hz=7680000, actual_rate_hz=7680000,
        actual_rf_bandwidth_hz=6000000, actual_lo_hz=98000000, RF_TX_requested=False,
        bus_phase=3, duration_requested_s=600, stopped_by_signal=False,
        elapsed_total_s=600, initial_stream=stream(0), final_stream=stream(600),
        input_samples_begin=0, input_samples_end=600*7680000,
        final_processing_status=dict(perf_status=0, lcd_status=0, cfar_status=0),
        measured_samples_per_second=7680000, median_display_fps=49,
        samples=[dict(elapsed_s=i, stream=stream(i), input_samples=i*7680000,
            fft_frames=i*3750, display_frames=i*49, display_fps=49,
            tx_atten_mdb=[89750,89750], rx_rssi_dbm=-60, temperature_c=45,
            perf_status=0) for i in range(1,601)])


def test_valid_whole_frame_drops_are_distinct_from_sample_loss():
    result = evaluate(measurement())
    assert result['sample_drop'] == 0
    assert result['frame_drop'] == 600


def screening_measurement():
    data = measurement()
    data.update(duration_requested_s=60, elapsed_total_s=60, test_scope='screening_60s',
                input_samples_end=60*7680000, samples=data['samples'][:60])
    data['final_stream'] = deepcopy(data['samples'][-1]['stream'])
    return data


def test_short_screen_cannot_pass_formal_acceptance():
    data = screening_measurement()
    assert evaluate(data, screening=True)['qualification'] == 'SCREENING_ONLY'
    with pytest.raises(ValueError):
        evaluate(data)


@pytest.mark.parametrize('case', ['loss', 'short', 'missing_scope', 'coverage', 'rssi'])
def test_screening_retains_loss_safety_and_coverage_gates(case):
    data = screening_measurement()
    if case == 'loss': data['initial_stream']['sample_drop'] = 1
    if case == 'short': data['elapsed_total_s'] = 59
    if case == 'missing_scope': data.pop('test_scope')
    if case == 'coverage': data['samples'] = data['samples'][:44]
    if case == 'rssi': data['samples'][2]['rx_rssi_dbm'] = -29
    with pytest.raises((ValueError, RuntimeError)):
        evaluate(data, screening=True)


@pytest.mark.parametrize('case', ['loss', 'initial_loss', 'reset', 'stale', 'bad_fps',
    'rssi', 'temperature', 'rf_bandwidth', 'short', 'throughput', 'frame_conservation', 'nan',
    'final_perf_error', 'final_lcd_error', 'final_cfar_error'])
def test_corrupt_metrics_rejected(case):
    data = deepcopy(measurement())
    if case == 'loss': data['samples'][2]['stream']['sample_drop'] = 1
    if case == 'initial_loss': data['initial_stream']['sample_drop'] = 1
    if case == 'reset': data['samples'][2]['stream']['frames_in'] = 0
    if case == 'stale': data['samples'][2]['input_samples'] = data['samples'][1]['input_samples']
    if case == 'bad_fps': data['samples'][2]['display_fps'] = 48
    if case == 'rssi': data['samples'][2]['rx_rssi_dbm'] = -29
    if case == 'temperature': data['samples'][2]['temperature_c'] = 86
    if case == 'rf_bandwidth': data['actual_rf_bandwidth_hz'] = 1500000
    if case == 'short': data['elapsed_total_s'] = 599
    if case == 'throughput': data['input_samples_end'] *= 2
    if case == 'frame_conservation': data['final_stream']['frames_in'] += 1
    if case == 'nan': data['samples'][2]['display_fps'] = float('nan')
    if case == 'final_perf_error': data['final_processing_status']['perf_status'] = 1
    if case == 'final_lcd_error': data['final_processing_status']['lcd_status'] = 4
    if case == 'final_cfar_error': data['final_processing_status']['cfar_status'] = 4
    with pytest.raises((ValueError, RuntimeError)):
        evaluate(data)
