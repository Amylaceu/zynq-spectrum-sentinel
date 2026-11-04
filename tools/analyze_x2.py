"""Independently recompute X2 bandwidth metrics from hashed board evidence."""
import argparse
import json
import math
from pathlib import Path
import statistics
import sys

from x2_transport import ROOT, sha, verified, write_evidence

sys.path.insert(0, str(ROOT/'src/ps'))
from sentinel.drivers.stream_x2 import StreamSnapshot

RATES = {7680000: 6000000, 15360000: 12000000, 24576000: 20000000, 30720000: 25000000}


def finite(value):
    if not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError('Non-finite numeric measurement')
    return value


def evaluate(data, *, screening=False):
    duration = 60 if screening else 600
    rate = data['requested_rate_hz']
    if (data['status'] != 'completed' or rate not in RATES or data['RF_TX_requested'] is not False
            or data['actual_rate_hz'] != rate or data['actual_rf_bandwidth_hz'] != RATES[rate]
            or abs(data['actual_lo_hz']-98000000) > 5 or data['bus_phase'] != 3
            or data['duration_requested_s'] != duration or data['stopped_by_signal']):
        raise ValueError('Incomplete or mismatched X2 RF run')
    if screening and data.get('test_scope') != 'screening_60s':
        raise ValueError('Explicit screening scope required')
    elapsed = finite(data['elapsed_total_s'])
    if not duration <= elapsed <= duration+10:
        raise ValueError('Incomplete or excessively delayed measurement window')
    previous = StreamSnapshot(**data['initial_stream'])
    previous.require_lossless()
    if previous.frames_in or previous.frames_out or previous.frame_drop:
        raise ValueError('Initial counters not zero')
    samples = data['samples']
    if len(samples) < int(duration*.75):
        raise ValueError('Insufficient telemetry coverage')
    last_time, last_input, last_fft, last_display = 0, data['input_samples_begin'], 0, None
    fps, temperatures = [], []
    for entry in samples:
        now = finite(entry['elapsed_s'])
        if not last_time < now <= elapsed or now-last_time > 5:
            raise ValueError('Stale/missing telemetry interval')
        snap = StreamSnapshot(**entry['stream'])
        snap.require_lossless()
        snap.require_monotonic(previous)
        if entry['input_samples'] <= last_input or entry['fft_frames'] <= last_fft:
            raise ValueError('Input/FFT processing stalled')
        display = entry['display_frames']
        if last_display is not None:
            delta = (display-last_display) & 0xffffffff
            actual_fps = delta/(now-last_time)
            if not delta or delta > 200*(now-last_time) or abs(actual_fps-finite(entry['display_fps'])) > .001:
                raise ValueError('Display liveness/fps mismatch')
        if (entry['tx_atten_mdb'] != [89750, 89750] or finite(entry['rx_rssi_dbm']) > -30
                or not 30 <= finite(entry['temperature_c']) <= 85 or entry['perf_status'] & 3):
            raise ValueError('Safety/temperature/performance status failed')
        fps.append(finite(entry['display_fps']))
        temperatures.append(entry['temperature_c'])
        previous, last_time = snap, now
        last_input, last_fft, last_display = entry['input_samples'], entry['fft_frames'], display
    if elapsed-last_time > 5:
        raise ValueError('Final telemetry gap')
    final = StreamSnapshot(**data['final_stream'])
    final.require_lossless()
    final.require_monotonic(previous)
    if final.frames_in != final.frames_out+final.frame_drop:
        raise ValueError('Final frame conservation fails')
    flags = data['final_processing_status']
    if flags['perf_status'] & 3 or flags['lcd_status'] & 0x1c or flags['cfar_status'] & 0x0c:
        raise ValueError('Final processing status fails')
    if data['input_samples_end'] < last_input:
        raise ValueError('Final sample counter decreased')
    throughput = (data['input_samples_end']-data['input_samples_begin'])/elapsed
    if abs(throughput/rate-1) > .01 or abs(throughput-data['measured_samples_per_second']) > .001:
        raise ValueError('Sample throughput inconsistent or out of tolerance')
    median = statistics.median(fps)
    if median < 15 or abs(median-data['median_display_fps']) > .001:
        raise ValueError('Median display fps fails')
    return dict(rate_hz=rate, rf_bandwidth_hz=RATES[rate], elapsed_s=elapsed,
        measured_samples_per_second=throughput, sample_drop=final.sample_drop,
        frame_drop=final.frame_drop, frames_in=final.frames_in, frames_out=final.frames_out,
        frame_drop_fraction=final.frame_drop/final.frames_in if final.frames_in else 0,
        median_display_fps=median, min_display_fps=min(fps),
        max_temperature_c=max(temperatures), telemetry_records=len(samples),
        qualification='SCREENING_ONLY' if screening else 'SUSTAINED_600S',
        scope='RX sample-throughput and display stability; no calibrated analog passband claim')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--measurement', type=Path, required=True)
    parser.add_argument('--screening', action='store_true', help='60-second screening only; never formal acceptance')
    args = parser.parse_args()
    path = args.measurement.resolve()
    data = verified(path)
    execution_path = path.with_name(path.stem+'_execution.json')
    execution = verified(execution_path)
    if (execution['status'] != 'PASS_EXECUTION' or execution['result_sha256'] != sha(path)
            or execution['boot_id_before'] != data['boot_id']
            or execution['postflight']['boot_id'] != data['boot_id']
            or execution['postflight']['status'] != 'PASS'):
        raise ValueError('Execution/boot/postflight evidence mismatch')
    metrics = evaluate(data, screening=args.screening)
    if bool(execution.get('screening', False)) != args.screening:
        raise ValueError('Execution scope differs from requested analysis')
    result = dict(status='PASS_SCREENING' if args.screening else 'PASS', metrics=metrics, measurement_sha256=sha(path),
                  execution_sha256=sha(execution_path), analyzer_sha256=sha(Path(__file__)))
    output = path.with_name(path.stem+'_acceptance.json')
    write_evidence(output, result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
