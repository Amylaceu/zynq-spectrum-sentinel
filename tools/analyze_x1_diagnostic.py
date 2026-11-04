"""Verify paired raw powers against hardware, then describe missed decisions.

Thresholds and hits here are GOLDEN MODEL RECONSTRUCTIONS, never hardware
measurements. Finite gated input is not a continuous-reception acceptance run.
"""
import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim.golden.cfar_x1 import detect_x1, mask_bins

from run_x1_board import sha, write_evidence

CONFIGURATION = {'average_shift': 3, 'mode': 'CA', 'n': 16, 'guard': 2,
                 'alpha': 1974, 'dc_mask': 3, 'min_width_bins': 2,
                 'merge_gap_bins': 6, 'mask_table': []}


def verify_hash(path):
    if sha(path) != Path(str(path) + '.sha256').read_text().split()[0]:
        raise ValueError('Evidence hash mismatch: ' + str(path))


def verify_receipt(data, execution, result_sha, archive_sha):
    if (execution['status'] != 'PASS_EXECUTION' or execution['ssh_exit_code'] != 0
            or execution['mode'] != data['source']
            or execution['result_sha256'] != result_sha
            or execution['archive_sha256'] != archive_sha
            or data['raw_archive_sha256'] != archive_sha
            or execution['boot_id_before'] != data['boot_id']
            or execution['preflight']['boot_id'] != data['boot_id']
            or execution['postflight']['boot_id'] != data['boot_id']):
        raise ValueError('Execution receipt/raw archive association mismatch')
    for state in (execution['preflight'], execution['postflight']):
        if state['status'] != 'PASS' or state['gpio_data'] != 0 or state['source_ctrl'] & 1:
            raise ValueError('Unsafe before/after stop state')
    if data['source'] == 'rf' and not execution['user_confirmed_rx1a_tx_empty']:
        raise ValueError('Missing user RF connection confirmation')


def segments(hit, power, blocked, gap, min_width):
    indices = np.flatnonzero(hit)
    groups = []
    if len(indices):
        start = previous = int(indices[0])
        for index in map(int, indices[1:]):
            if index - previous - 1 > gap or blocked[previous + 1:index].any():
                groups.append((start, previous))
                start = index
            previous = index
        groups.append((start, previous))
    rows = []
    for start, stop in groups:
        peak = start + int(np.argmax(power[start:stop + 1]))
        rows.append({'start': start, 'stop': stop, 'peak_bin': peak,
                     'peak_power': int(power[peak]), 'width_bins': stop-start+1,
                     'passes_min_width': stop-start+1 >= min_width})
    ordered = sorted((r for r in rows if r['passes_min_width']),
                     key=lambda r: (-r['peak_power'], r['start']))
    for rank, row in enumerate(ordered):
        row.update(rank=rank, kept_top32=rank < 32)
    return rows


def decision_trace(hit, power, cluster, blocked, lo=96400000, rate=3840000):
    """Explain algorithm decisions near the fixed, predeclared test frequency."""
    frequency = lo + (np.arange(2048) - 1024) * rate / 2048
    target = np.abs(frequency - 95800000) <= 25000
    low, high = map(int, (np.flatnonzero(target)[0], np.flatnonzero(target)[-1]))
    groups = segments(hit, power, blocked, gap=6, min_width=2)
    nearby = [g for g in groups if g['start'] <= high and g['stop'] >= low]
    detected = any(target[int(t['peak_bin'])] for t in cluster.targets)
    labels = []
    if detected:
        labels.append('published_peak_in_tolerance')
    else:
        if not hit[target].any():
            labels.append('no_post_mask_hit_in_tolerance')
        if any(not g['passes_min_width'] for g in nearby):
            labels.append('width_filtered_segment_in_tolerance')
        if any(g['passes_min_width'] and not target[g['peak_bin']] for g in nearby):
            labels.append('overlapping_segment_peak_outside_tolerance')
        if any(g['passes_min_width'] and target[g['peak_bin']] and not g['kept_top32'] for g in nearby):
            labels.append('in_tolerance_peak_lost_to_top32')
    return {'station_peak_detected': bool(detected), 'labels': labels,
            'hit_bins_in_tolerance': int(hit[target].sum()),
            'segments_overlapping_tolerance': nearby,
            'published_interval_overlaps_tolerance': any(
                int(t['start']) <= high and int(t['stop']) >= low for t in cluster.targets)}


def reconstruct(data, powers):
    samples = data['samples']
    if (data['status'] != 'completed' or data['source'] not in ('test', 'rf')
            or data['RF_TX_requested'] is not False or data['configuration'] != CONFIGURATION
            or data['lo_hz'] != 96400000 or data['rate_hz'] != 3840000
            or data['rf_bandwidth_hz'] != 1500000 or data['warmup_frames'] != 64
            or not 4 <= len(samples) == data['requested_frames'] <= 128):
        raise ValueError('Incomplete or incompatible diagnostic configuration')
    if powers.shape != (len(samples), 2048) or powers.dtype != np.dtype('uint32'):
        raise ValueError('Raw power shape/dtype mismatch')
    warmup = data['warmup_association']
    if (warmup['cfar_before'] != 0 or warmup['source_frames'] != 64 or warmup['source_samples'] != 131072
            or warmup['spec_sequence'] != 64 or warmup['perf_delta'] != [131072, 64, 64]
            or warmup['perf_status'] & 3):
        raise ValueError('Invalid finite warmup association')
    thresholds, hits, traces = [], [], []
    blocked = mask_bins(2048, (), 3)
    previous, token, elapsed = 64, None, -1
    for index, (row, power) in enumerate(zip(samples, powers)):
        assoc, seq = row['association'], (previous + 1) & 0xffffffff
        if (row['index'] != index or assoc['cfar_before'] != previous or row['cfar_sequence'] != seq
                or assoc['source_frames'] != 1 or assoc['source_samples'] != 2048
                or assoc['spec_sequence'] != seq or assoc['perf_delta'] != [2048, 1, 1]
                or assoc['perf_status'] & 3 or assoc['capture_token'] not in (0, 1)
                or assoc['capture_token'] == token or not np.isfinite(row['elapsed_s'])
                or row['elapsed_s'] <= elapsed):
            raise ValueError('Stale or unpaired frame at index %d' % index)
        for safety in (row, row['safety_before']):
            if not np.isfinite(safety['temperature_c']) or not 30 <= safety['temperature_c'] <= 85:
                raise ValueError('Invalid temperature in frame %d' % index)
            if data['source'] == 'rf' and (safety['tx_atten_mdb'] != [89750, 89750]
                    or not np.isfinite(safety['rx_rssi_dbm']) or safety['rx_rssi_dbm'] > -30):
                raise ValueError('Unsafe RF frame %d' % index)
            if data['source'] == 'rf' and (
                    abs(safety['actual_lo_hz'] - data['lo_hz']) > 5
                    or safety['actual_rate_hz'] != data['rate_hz']):
                raise ValueError('Incorrect RF readback in frame %d' % index)
        if data['source'] == 'test':
            tone = (64, -300, 300, -128)[index % 4]
            if row['test_tone_bin'] != tone or power[1024+tone] == 0:
                raise ValueError('Missing or incorrect digital test tone')
        threshold, hit, cluster = detect_x1(power)
        expected = {'hit_count': cluster.hit_count, 'raw_count': cluster.raw_count,
                    'filtered_count': cluster.filtered_count, 'candidate_count': cluster.candidate_count,
                    'status_latch': cluster.status_latch, 'list_overflow': cluster.overflow}
        for field, value in expected.items():
            if row[field] != value:
                raise ValueError('Hardware/model mismatch frame %d field %s' % (index, field))
        targets = [dict(start=int(t['start']), stop=int(t['stop']), peak_bin=int(t['peak_bin']),
                        flags=int(t['flags']), peak_power=int(t['peak_pwr']), sum_power=int(t['sum_pwr']))
                   for t in cluster.targets]
        if targets != row['targets']:
            raise ValueError('Hardware/model target mismatch at frame %d' % index)
        thresholds.append(threshold)
        hits.append(hit)
        traces.append(dict(index=index, cfar_sequence=seq, **decision_trace(hit, power, cluster, blocked,
            lo=row.get('actual_lo_hz', data['lo_hz']), rate=row.get('actual_rate_hz', data['rate_hz']))))
        previous, token, elapsed = seq, assoc['capture_token'], row['elapsed_s']
    return np.stack(thresholds), np.stack(hits), blocked, traces


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output-prefix', type=Path,
                        help='New evidence prefix for a numbered analysis retry; never overwrites prior files')
    args = parser.parse_args()
    args.input = args.input.resolve()
    prefix = args.output_prefix.resolve() if args.output_prefix else args.input.with_suffix('')
    prefix.relative_to(ROOT)
    output = prefix.with_name(prefix.name + '_analysis.json')
    reconstruction = prefix.with_name(prefix.name + '_model.npz')
    for path in (output, reconstruction):
        if path.exists() or Path(str(path)+'.sha256').exists():
            parser.error('Preserve prior analysis: ' + str(path))
    archive = args.input.with_suffix('.npz')
    receipt = args.input.with_name(args.input.stem + '_execution.json')
    for path in (args.input, archive, receipt):
        verify_hash(path)
    data = json.loads(args.input.read_text())
    execution = json.loads(receipt.read_text())
    verify_receipt(data, execution, sha(args.input), sha(archive))
    if sha(ROOT/execution['log']) != execution['log_sha256']:
        raise ValueError('Execution log hash mismatch')
    frozen = ROOT/'docs/x1_software_predeployment_r3.json'
    if sha(frozen) != execution['frozen_software_manifest_sha256']:
        raise ValueError('Frozen input manifest hash mismatch')
    acceptance = json.loads((ROOT/'board/overlay/sentinel_v1b/acceptance.json').read_text())
    if data['artifacts_sha256'] != acceptance['artifacts_sha256']:
        raise ValueError('Hardware bundle association mismatch')
    for relative, digest in execution['diagnostic_sources_sha256'].items():
        archived = ROOT/'data/reference/diagnostics/x1_sources'/digest/Path(relative).name
        if sha(ROOT/relative) != digest and (not archived.exists() or sha(archived) != digest):
            raise ValueError('Diagnostic input changed: ' + relative)
    with np.load(archive, allow_pickle=False) as raw:
        powers = raw['power']
    threshold, hit, blocked, traces = reconstruct(data, powers)
    with reconstruction.open('xb') as stream:
        np.savez_compressed(stream, model_threshold=threshold, model_hit=hit, model_mask=blocked)
    Path(str(reconstruction)+'.sha256').write_text(sha(reconstruction)+'  '+reconstruction.name+'\n')
    labels = Counter(label for row in traces for label in row['labels'])
    record = {'status': 'PASS_PAIRING', 'recorded_at_pc': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
              'scope': 'Finite gated-frame hardware/model equivalence and decision traces only; X1 RF acceptance unchanged',
              'model_origin': 'Threshold/hit/mask reconstructed on PC, not measured hardware outputs',
              'physical_limits': 'No raw IQ or independent truth source; cannot infer actual station presence or RF cause',
              'source': data['source'], 'paired_frames': len(traces), 'exact_power_words': int(powers.size),
              'exact_counter_fields': 6*len(traces),
              'target_records_exact': sum(len(s['targets']) for s in data['samples']),
              'station_detected_frames': sum(t['station_peak_detected'] for t in traces),
              'decision_label_counts': dict(labels), 'labels_may_overlap': True, 'frames': traces,
              'configuration': data['configuration'],
              'evidence_sha256': {p.relative_to(ROOT).as_posix(): sha(p) for p in (args.input, archive, receipt, reconstruction)},
              'source_sha256': {p: sha(ROOT/p) for p in (
                  'tools/analyze_x1_diagnostic.py', 'sim/golden/cfar_x1.py', 'sim/golden/cfar.py')}}
    write_evidence(output, record)
    print(json.dumps({k:v for k,v in record.items() if k not in ('frames','evidence_sha256','source_sha256')}, indent=2))


if __name__ == '__main__':
    main()
