"""Audit historical antenna windows and replay frozen powers without board access.

95.45 MHz is a user-reported supplementary observation, not station ground truth
or a replacement for the declared 95.8 MHz acceptance target. Counterfactual
configurations are model results only; no deployment or acceptance is performed.
"""

import argparse
from datetime import datetime
import json
from pathlib import Path
import statistics
from zoneinfo import ZoneInfo

import numpy as np

from analyze_antenna_comparison import audit_run, read_verified, reference
from analyze_x1_diagnostic import (
    CONFIGURATION, reconstruct, verify_hash, verify_receipt,
)
from run_x1_board import ROOT, sha, write_evidence
from sim.golden.cfar_x1 import detect_x1


FREQUENCIES = (95450000, 95800000)
TOLERANCE_HZ = 25000
ANTENNA_RUNS = (
    ('long_r1', 'long'), ('short_r1', 'short'), ('third_r1', 'third'),
    ('short_r2', 'short'), ('new_r1', 'new'),
)
# Fixed one-factor contrasts. No grid search, parameter fitting or selection.
CONTRASTS = (
    ('baseline', {}, 'Frozen deployed configuration'),
    ('width_one', {'min_width_bins': 1},
     'Diagnostic only: admits isolated bins and may increase nuisance targets'),
    ('gap_two', {'merge_gap_bins': 2}, 'Less merging; may split one signal'),
    ('gap_twelve', {'merge_gap_bins': 12}, 'More merging; may fuse distinct signals'),
    ('guard_eight', {'g': 8}, 'Moves reference window farther from each CUT'),
    ('guard_sixteen', {'g': 16}, 'Moves reference window farther from each CUT'),
    ('references_32', {'n': 32}, 'Averages a wider reference region'),
    ('references_64', {'n': 64}, 'Averages a wider reference region'),
    ('alpha_1536', {'alpha_q88': 1536}, 'Lower threshold; capacity risk retained'),
    ('smaller_side', {'mode': 'SO'},
     'Uses the quieter reference side; fixed alpha is not a matched-Pfa calibration'),
)


def frequency_summary(rows, lo_hz, rate_hz, frequency_hz):
    """Count published peaks once per attempt, including missing snapshots."""
    if not rows:
        raise ValueError('Empty attempt set')
    detected, peaks, powers, widths = [], [], [], []
    for index, row in enumerate(rows):
        if not row.get('snapshot_available', True):
            continue
        matches = [target for target in row['targets']
                   if abs(lo_hz + (target['peak_bin'] - 1024) * rate_hz / 2048
                          - frequency_hz) <= TOLERANCE_HZ]
        if matches:
            # Extra in-band peaks do not inflate the detection denominator.
            strongest = max(matches, key=lambda target: target['peak_power'])
            detected.append(index)
            peaks.append(lo_hz + (strongest['peak_bin'] - 1024) * rate_hz / 2048)
            powers.append(strongest['peak_power'])
            widths.append(strongest['stop'] - strongest['start'] + 1)
    return {
        'frequency_hz': frequency_hz, 'tolerance_hz': TOLERANCE_HZ,
        'attempts': len(rows), 'detected_attempts': len(detected),
        'detection_rate_all_attempts': len(detected) / len(rows),
        'detected_frame_indices': detected,
        'peak_frequency_hz_median': statistics.median(peaks) if peaks else None,
        'peak_frequency_hz_range': [min(peaks), max(peaks)] if peaks else None,
        'peak_power_integer_median': statistics.median(powers) if powers else None,
        'cluster_width_bins_median': statistics.median(widths) if widths else None,
    }


def verify_diagnostic(path):
    """Require original receipts, raw data, software and hardware associations."""
    archive = path.with_suffix('.npz')
    receipt_path = path.with_name(path.stem + '_execution.json')
    for item in (path, archive, receipt_path):
        verify_hash(item)
    data = read_verified(path)
    receipt = read_verified(receipt_path)
    verify_receipt(data, receipt, sha(path), sha(archive))
    if data['source'] != 'rf':
        raise ValueError('This report requires the frozen RF diagnostic')
    log = ROOT / receipt['log']
    if sha(log) != receipt['log_sha256']:
        raise ValueError('Diagnostic execution log changed')
    frozen_path = ROOT / 'docs/x1_software_predeployment_r3.json'
    frozen = read_verified(frozen_path)
    if sha(frozen_path) != receipt['frozen_software_manifest_sha256']:
        raise ValueError('Frozen manifest association changed')
    for relative, digest in frozen['source_sha256'].items():
        if sha(ROOT / relative) != digest:
            raise ValueError('Frozen software changed: ' + relative)
    for relative, digest in receipt['diagnostic_sources_sha256'].items():
        archived = ROOT / 'data/reference/diagnostics/x1_sources' / digest / Path(relative).name
        if sha(ROOT / relative) != digest and (not archived.exists() or sha(archived) != digest):
            raise ValueError('Diagnostic source changed: ' + relative)
    acceptance_path = ROOT / 'board/overlay/sentinel_v1b/acceptance.json'
    acceptance = read_verified(acceptance_path)
    if data['artifacts_sha256'] != acceptance['artifacts_sha256']:
        raise ValueError('Diagnostic hardware association changed')
    for name, digest in data['artifacts_sha256'].items():
        if Path(name).name != name:
            raise ValueError('Hardware name must be a basename')
        if sha(ROOT / 'board/overlay/sentinel_v1b' / name) != digest:
            raise ValueError('Diagnostic artifact changed: ' + name)
    with np.load(archive, allow_pickle=False) as raw:
        powers = raw['power']
    # Must match ALL original hardware counts/targets before exploring contrasts.
    _, _, _, traces = reconstruct(data, powers)
    return data, powers, traces, [reference(item) for item in (
        path, archive, receipt_path, log, frozen_path, acceptance_path)]


def replay(data, powers, changes):
    parameters = dict(mode='CA', n=16, g=2, alpha_q88=1974, dc_mask=3,
                      min_width_bins=2, merge_gap_bins=6, mask_table=())
    parameters.update(changes)
    frames = []
    for sample, power in zip(data['samples'], powers):
        threshold, hit, cluster = detect_x1(power, **parameters)
        lo = sample['actual_lo_hz']
        rate = sample['actual_rate_hz']
        targets = [dict(start=int(t['start']), stop=int(t['stop']),
                        peak_bin=int(t['peak_bin']), peak_power=int(t['peak_pwr']))
                   for t in cluster.targets]
        frame = dict(index=sample['index'], targets=targets,
                     candidate_count=cluster.candidate_count,
                     capacity_alarm=bool(cluster.overflow), frequencies={})
        frequencies = lo + (np.arange(2048) - 1024) * rate / 2048
        for frequency in FREQUENCIES:
            region = np.flatnonzero(np.abs(frequencies - frequency) <= TOLERANCE_HZ)
            peak = int(region[np.argmax(power[region])])
            left = sum(int(power[(peak - offset) % 2048])
                       for offset in range(parameters['g'] + 1,
                                           parameters['g'] + parameters['n'] + 1))
            right = sum(int(power[(peak + offset) % 2048])
                        for offset in range(parameters['g'] + 1,
                                            parameters['g'] + parameters['n'] + 1))
            frame['frequencies'][str(frequency)] = {
                'strongest_cut_bin': peak, 'cut_power': int(power[peak]),
                'model_threshold': int(threshold[peak]),
                'model_post_mask_hit_bins': int(hit[region].sum()),
                'left_reference_mean': left / parameters['n'],
                'right_reference_mean': right / parameters['n'],
            }
        frames.append(frame)
    # Two chronological halves describe sensitivity; they are not held-out tests.
    slices = {'all': frames, 'early_half': frames[:len(frames)//2],
              'late_half': frames[len(frames)//2:]}
    summary = {}
    for name, rows in slices.items():
        summary[name] = {
            'frames': len(rows),
            'capacity_alarm_frames': sum(row['capacity_alarm'] for row in rows),
            'candidate_count_median': statistics.median(row['candidate_count'] for row in rows),
            'frequencies': {str(frequency): frequency_summary(
                rows, data['samples'][0]['actual_lo_hz'], data['rate_hz'], frequency)
                for frequency in FREQUENCIES},
        }
    return {'model_parameters': parameters, 'summary': summary, 'frames': frames}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnostic', type=Path,
                        default=Path('board/measurements/x1_diagnostic_rf_r2.json'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    output = (ROOT / args.out).resolve()
    output.relative_to(ROOT)
    if output.exists() or Path(str(output) + '.sha256').exists():
        parser.error('Preserve previous evidence; use a new output name')
    antenna_records, previous, shared = {}, None, None
    for tag, antenna in ANTENNA_RUNS:
        path = ROOT / ('board/measurements/antenna_compare_' + tag + '.json')
        data, _, audited = audit_run(path, antenna)
        identity = {key: data[key] for key in (
            'configuration', 'actual_lo_hz', 'actual_rate_hz', 'rf_bandwidth_hz',
            'bus_phase', 'artifacts_sha256', 'boot_id')}
        if shared is not None and identity != shared:
            raise ValueError('Antenna comparison configuration changed: ' + tag)
        if (previous is not None and datetime.fromisoformat(previous)
                > datetime.fromisoformat(audited['started_at_pc'])):
            raise ValueError('Antenna windows overlap or are reversed')
        previous, shared = audited['ended_at_pc'], identity
        antenna_records[tag] = {
            'audited_window': audited,
            'frequencies': {str(frequency): frequency_summary(
                data['samples'], data['actual_lo_hz'], data['actual_rate_hz'], frequency)
                for frequency in FREQUENCIES},
        }
    diagnostic, powers, traces, evidence = verify_diagnostic((ROOT / args.diagnostic).resolve())
    contrasts = {}
    for name, changes, rationale in CONTRASTS:
        contrasts[name] = dict(replay(diagnostic, powers, changes), rationale=rationale)
    baseline = contrasts['baseline']['summary']['all']['frequencies']['95800000']
    if baseline['detected_attempts'] != sum(row['station_peak_detected'] for row in traces):
        raise ValueError('Baseline replay differs from audited hardware target decisions')
    sources = (
        'tools/analyze_x1_frozen_replay.py', 'tools/analyze_antenna_comparison.py',
        'tools/analyze_x1_board.py', 'tools/analyze_x1_diagnostic.py',
        'sim/golden/cfar_x1.py', 'sim/golden/cfar.py',
    )
    record = {
        'status': 'COMPLETED_OFFLINE_REPLAY',
        'recorded_at_pc': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'scope': 'Historical antenna audit and finite gated RF power model contrasts only',
        'user_observation': '95.45 MHz was detected frequently with both antennas',
        'original_acceptance_frequency_hz': 95800000,
        'supplementary_frequency_hz': 95450000, 'tolerance_hz': TOLERANCE_HZ,
        'x1_acceptance_unchanged': 'FAIL; three original RF rounds retained',
        'board_operations_performed': False, 'parameters_deployed': False,
        'selection_performed': False, 'antenna_windows': antenna_records,
        'diagnostic_configuration': CONFIGURATION, 'diagnostic_evidence': evidence,
        'diagnostic_frames': len(powers), 'contrasts': contrasts,
        'source_sha256': {relative: sha(ROOT / relative) for relative in sources},
        'limitations': [
            'No independent RF truth: a stable peak is not proof of a broadcast station.',
            '95.45 MHz is -950 kHz from LO, outside the nominal +/-750 kHz RF band; '
            'filter rolloff is not a brick wall and this observation does not extend rated bandwidth.',
            'Historical sequential windows do not establish stable antenna ranking.',
            'Power is uncalibrated integer data; no antenna gain or calibrated SNR is inferred.',
            'Replay thresholds, hits and alternate targets are PC model outputs only.',
            'Fixed SO alpha does not preserve CA false-alarm probability.',
            'Early/late halves are correlated descriptive slices, not independent validation.',
            'Only 96 gated power frames at LO 96.4 MHz; no continuous capacity-window replay.',
            'No raw IQ, carrier identity, modulation or RF physical cause is established.',
        ],
    }
    write_evidence(output, record)
    print(json.dumps({
        'output': output.relative_to(ROOT).as_posix(), 'status': record['status'],
        'antenna_detection_counts': {tag: {frequency: result['detected_attempts']
            for frequency, result in row['frequencies'].items()}
            for tag, row in antenna_records.items()},
        'replay': {name: value['summary']['all'] for name, value in contrasts.items()},
    }, indent=2))


if __name__ == '__main__':
    main()
