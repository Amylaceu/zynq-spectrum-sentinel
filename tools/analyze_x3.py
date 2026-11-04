"""Recompute X3 comparisons from immutable raw measurements; no board access.

Run from any directory with the repository Python. Existing output is preserved.
An acquisition FAIL can contain a valid, complete digital subtest; RF is a
separate gate and is never inferred from the digital subtest's completion.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim.golden.cfar import cfar
from analyze_v1_selftest import verify


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checked(path):
    require(sha(path) == Path(str(path)+'.sha256').read_text().split()[0],
            'Evidence digest mismatch: '+str(path))
    return json.loads(path.read_text(encoding='utf-8-sig'))


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    Path(str(path)+'.sha256').write_text(sha(path)+'  '+path.name+'\n', encoding='ascii')


def analyze_digital(data):
    latency = data['latency']
    rows = latency['samples']
    require(len(rows) == 1000 and latency['average_shift'] == 0, 'Need 1000 unaveraged measurements')
    require(latency['clock_hz'] == 150000000 and latency['rate_hz'] == 3840000,
            'Unexpected measurement clock/rate')
    previous = None
    for i, row in enumerate(rows):
        before, after = row['before'], row['after']
        require(row['iteration'] == i and row['expected_peak_bin'] == 1056+i % 128
                and row['peak_bin'] == row['expected_peak_bin']
                and row['peak_bin'] in row['target_peak_bins'], 'Tone association failed')
        require(after['status'] == 4 and not before['status'] & 0x1b
                and after['markers_done'] == i+1 and before['markers_done'] == i
                and after['latency_cycles'] > 0, 'Invalid marker/status')
        for name, delta in (('samples', 2048), ('fft_frames', 1), ('lists', 1)):
            require(after[name]-before[name] == delta, 'Finite-frame counter mismatch: '+name)
            if previous:
                require(before[name] == previous[name], 'Unaccounted intervening frame/sample')
        previous = after
    times = np.array([row['after']['latency_cycles'] for row in rows])/latency['clock_hz']*1e6
    throughput = data['digital_throughput']
    a, b = throughput['before'], throughput['after']
    require(a['status'] == b['status'] == 4 and a['markers_done'] == b['markers_done'] == 1000,
            'Digital throughput has error or extra marker')
    elapsed = (b['cycles']-a['cycles'])/throughput['clock_hz']
    samples = b['samples']-a['samples']
    frames = b['fft_frames']-a['fft_frames']
    require(elapsed >= 3 and samples > 0 and frames == b['lists']-a['lists'] > 0,
            'Invalid throughput interval')
    require(abs(samples/elapsed/latency['rate_hz']-1) < .001, 'Actual IQ rate inconsistent')
    require(abs(frames-samples/2048) <= 2, 'Power-frame event count inconsistent')
    cpu = data['cpu']
    fixture = cpu['detector_fixture']
    params = cpu['detector_parameters']
    threshold, hits = cfar(np.array(fixture['power'], dtype=np.uint32), n=params['n'],
                          g=params['guard'], alpha_q88=params['alpha'], dc_mask=params['dc_mask'])
    require(np.array_equal(threshold, fixture['threshold']) and np.array_equal(hits, fixture['hits']),
            'Independent CA golden mismatch')
    medians = {}
    for name, count in (('fft2048', 1000), ('cfar2048', 200), ('pillow800x480_render_only', 200)):
        array = np.array(cpu[name]['samples_s'])
        require(array.shape == (count,) and np.all(np.isfinite(array)) and np.all(array > 0),
                'Invalid CPU duration samples')
        medians[name] = float(np.median(array))
    acquisition = (2048-1)/latency['rate_hz']*1e6
    return {'count':len(rows), 'latency_median_us':float(np.median(times)),
            'latency_max_us':float(times.max()), 'latency_min_us':float(times.min()),
            'latency_under_200us':'PASS' if times.max() < 200 else 'FAIL',
            'definition':latency['definition'], 'acquisition_first_to_last_us':acquisition,
            'derived_median_remainder_us':float(np.median(times))-acquisition,
            'remainder_scope':'Derived subtraction; NOT an independently measured CFAR latency',
            'throughput_window_s':elapsed, 'actual_iq_samples_per_s':samples/elapsed,
            'post_welch_frames_per_s_avg0':frames/elapsed,
            'cpu_kernel_median_s':medians, 'cpu_ca_golden':'PASS',
            'fft_only_speedup_current':frames/elapsed*medians['fft2048'],
            'fft_ca_kernel_throughput_ratio_current':frames/elapsed*(medians['fft2048']+medians['cfar2048']),
            'comparison_scope':'CPU FFT+integer CA excludes X1 clustering/top32; PL includes them. '
                               'Throughput ratio is not per-frame latency speedup.'}


def analyze_receive(data):
    require(data['status'] == 'completed' and not data['RF_TX_requested'], 'Receive acquisition not complete')
    baseline = data['receive_initialization']['after_clear_before_start']
    require(all(baseline[k] == 0 for k in ('status', 'samples', 'fft_frames', 'lists')),
            'Receive baseline was not zero')
    rx = data['receive']
    rows = rx['samples']
    require(rx['elapsed_total_s'] >= 30 and len(rows) >= 20 and rx['actual_rate_hz'] == 3840000,
            'Receive window too short or wrong rate')
    for row in rows:
        require(row['perf']['status'] & 3 == 0 and row['tx_atten_mdb'] == [89750, 89750]
                and row['rssi_dbm'] <= -30 and 30 <= row['temperature_c'] <= 85,
                'Unsafe/invalid receive sample')
        require(row['interval_s'] > 0 and row['display_frame_delta'] > 0, 'Invalid display counter interval')
    fps = [row['display_frame_delta']/row['interval_s'] for row in rows]
    return {'status':'PASS_30S_WINDOW', 'display_median_fps':float(np.median(fps)),
            'display_min_fps':float(min(fps)), 'telemetry_samples':len(rows),
            'max_temperature_c':max(row['temperature_c'] for row in rows),
            'cpu_window':rx['cpu_window'], 'scope':rx['scope'],
            'before_clear_status':data['receive_initialization']['before_clear']['status'],
            'after_clear_status':baseline['status'],
            'scope_limit':'Short observation, not long-term/full-bandwidth acceptance; no new human visual check'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--digital', type=Path, default=ROOT/'board/measurements/x3_perf_r3.json')
    p.add_argument('--receive', type=Path, default=ROOT/'board/measurements/x3_receive_r2.json')
    p.add_argument('--out', type=Path, default=ROOT/'board/measurements/x3_analysis.json')
    args = p.parse_args()
    require(not args.out.exists(), 'Preserve prior analysis')
    inputs = {}
    def record(path):
        inputs[path.relative_to(ROOT).as_posix()] = sha(path)
    digital = checked(args.digital)
    receipt_path = args.digital.with_name(args.digital.stem+'_execution.json')
    receipt = checked(receipt_path)
    require(receipt['measurement_sha256'] == sha(args.digital), 'Digital receipt mismatch')
    for measurement, receipt_file in ((args.digital, receipt_path),
            (args.receive, args.receive.with_name(args.receive.stem+'_execution.json'))):
        received = checked(receipt_file)
        require(received['measurement_sha256'] == sha(measurement)
                and received['postflight']['status'] == 'PASS'
                and received['library_sha256_before'] == received['library_sha256_after']
                and received['preflight']['boot_id'] == received['postflight']['boot_id'],
                'Execution/safe-cleanup provenance mismatch')
        require(checked(measurement)['boot_id'] == received['postflight']['boot_id'], 'Measurement boot differs')
        record(measurement); record(receipt_file)
    rx_receipt = checked(args.receive.with_name(args.receive.stem+'_execution.json'))
    require(rx_receipt['status'] == 'PASS_EXECUTION', 'Receive runner did not pass')
    d = analyze_digital(digital)
    rx = analyze_receive(checked(args.receive))
    baseline_path = ROOT/'board/measurements/p5_cpu_baseline.json'
    display_path = ROOT/'board/measurements/lcd_font_runtime.json'
    baseline = json.loads(baseline_path.read_text())['cpu_baseline']
    display = json.loads(display_path.read_text())
    record(baseline_path); record(display_path)
    rate = d['post_welch_frames_per_s_avg0']
    d['fft_only_speedup_historical'] = rate*baseline['fft2048_median_s']
    d['fft_ca_kernel_throughput_ratio_historical'] = rate*(baseline['fft2048_median_s']+baseline['cfar2048_median_s'])
    g1_path = ROOT/'board/measurements/n4_selftest_round2.json'
    g1_bit = ROOT/'board/overlay/sentinel_v1/sentinel_v1.bit'
    g1 = verify(g1_path, ROOT/'data/reference/spectrum', g1_bit)
    for path in (g1_path, g1_path.with_suffix('.npz'), g1_bit,
                 ROOT/'data/reference/spectrum/in_axis32.hex', ROOT/'data/reference/spectrum/exp_power_shifted.hex'):
        record(path)
    g1.update(gate='G1', scope='Independent re-verification of N4 finite test/replay; not X2 width or RF quality')
    save(args.out.with_name('x3_g1_acceptance.json'), g1)
    phases = []
    for phase in (25, 12, 8, 6, 4, 3, 2):
        path = ROOT/('board/measurements/n4_bench_phase%d_%s.json' % (
            phase, 'round1' if phase == 25 else 'ui_r1'))
        raw = json.loads(path.read_text())
        require(abs(raw['display_fps']-raw['display_frames']/raw['elapsed_s']) < 1e-6,
                'Historical display counter mismatch')
        record(path)
        phases.append({'bus_phase':phase, 'fps':raw['display_fps'], 'scope':'10s pure spectrum/waterfall; no PS text updates'})
    utilization = ROOT/'build/reports/live_z20_lcd/system_top_utilization_placed.rpt'
    require('| Block RAM Tile    |   68 |' in utilization.read_text(), 'CPU display BRAM report differs')
    record(utilization)
    accepted = checked(ROOT/'board/overlay/sentinel_v1b/acceptance.json')
    record(ROOT/'board/overlay/sentinel_v1b/acceptance.json')
    result = {'status':'FAIL_ORIGINAL_X3_TARGETS', 'digital':d, 'receive':rx,
              'historical_cpu':baseline, 'display':{'cpu_fullchain_fps':display['update_fps'],
              'cpu_fullchain_cpu_percent':'NOT_MEASURED', 'cpu_bram':68, 'n4_v1_bram':49,
              'current_v1b_bram':accepted['resources']['Block RAM Tile'],
              'pl_to_cpu_display_ratio':rx['display_median_fps']/display['update_fps'], 'phases':phases},
              'bandwidth':[{'rate_hz':rate, 'status':'NOT_TESTED', 'reason':'X2 routed timing failed; bitstream never loaded'}
                           for rate in (7680000, 15360000, 24576000, 30720000)],
              'g1':'DONE', 'milestone_a':'CHECKPOINT_WITH_UNMET_X1_X2_X3_TARGETS',
              'inputs_sha256':inputs, 'analysis_source_sha256':sha(Path(__file__))}
    save(args.out, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
