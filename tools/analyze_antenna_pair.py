"""Compare two explicitly labeled receive-only windows without board operations.

Reuse the audited metrics and preserve historical comparisons. Raw inputs,
execution receipts, logs, hardware and frozen software must match their hashes.
"""

import argparse
from datetime import datetime
from pathlib import Path
import json
from zoneinfo import ZoneInfo

from analyze_antenna_comparison import audit_run, read_verified, reference
from run_x1_board import ROOT, sha, write_evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--baseline-antenna', required=True)
    parser.add_argument('--candidate', required=True, type=Path)
    parser.add_argument('--candidate-antenna', required=True)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--confirm-same-placement', action='store_true',
                        help='Record explicit user confirmation of fixed position and orientation')
    args = parser.parse_args()
    output = (ROOT / args.out).resolve()
    if output.exists() or Path(str(output) + '.sha256').exists():
        parser.error('Preserve previous comparison evidence')
    runs, receipts, records = {}, {}, {}
    for role, path, antenna in (
        ('baseline', args.baseline, args.baseline_antenna),
        ('candidate', args.candidate, args.candidate_antenna),
    ):
        runs[role], receipts[role], records[role] = audit_run(
            (ROOT / path).resolve(), antenna)
    first, second = runs['baseline'], runs['candidate']
    for key in ('configuration', 'actual_lo_hz', 'actual_rate_hz',
                'rf_bandwidth_hz', 'bus_phase', 'artifacts_sha256', 'boot_id'):
        if first[key] != second[key]:
            raise ValueError('Comparison inputs differ: ' + key)
    if receipts['baseline']['monitor_sha256'] != receipts['candidate']['monitor_sha256']:
        raise ValueError('Monitor software differs')
    if (datetime.fromisoformat(records['baseline']['ended_at_pc'])
            > datetime.fromisoformat(records['candidate']['started_at_pc'])):
        raise ValueError('Measurement windows overlap or are reversed')
    frozen_path = ROOT / 'docs/x1_software_predeployment_r3.json'
    frozen = read_verified(frozen_path)
    for relative, digest in frozen['source_sha256'].items():
        if sha(ROOT / relative) != digest:
            raise ValueError('Frozen software changed: ' + relative)
    delta = (records['candidate']['metrics']['station_detection_rate_all_attempts']
             - records['baseline']['metrics']['station_detection_rate_all_attempts'])
    better = 'candidate' if delta > 0 else 'baseline' if delta < 0 else 'tie'
    result = {
        'status': 'COMPLETED_ANTENNA_PAIR_COMPARISON',
        'recorded_at_pc': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'scope': 'Two sequential 120s receive-only windows; not full X1 acceptance',
        'station_hz': 95800000, 'tolerance_hz': 25000,
        'configuration': first['configuration'],
        'actual_lo_hz': first['actual_lo_hz'],
        'actual_rate_hz': first['actual_rate_hz'],
        'rf_bandwidth_hz': first['rf_bandwidth_hz'],
        'bus_phase': first['bus_phase'], 'boot_id': first['boot_id'],
        'artifacts_sha256': first['artifacts_sha256'],
        'monitor_sha256': receipts['baseline']['monitor_sha256'],
        'frozen_software': reference(frozen_path),
        'frozen_software_files_verified': len(frozen['source_sha256']),
        'runs': records,
        'human_confirmed_same_placement': args.confirm_same_placement,
        'candidate_minus_baseline_detection_percentage_points': delta * 100,
        'observed_higher_station_detection_role': better,
        'x1_acceptance_unchanged': 'FAIL; no 98MHz capacity window in this comparison',
        'limitations': [
            'Preference applies only to this station and placement, not full-band antenna gain.',
            'Sequential windows can differ with time, multipath, placement and contact quality.',
            'Receiver-reported RSSI is not calibrated target SNR or antenna gain.',
            'The denominator counts scheduled telemetry attempts, not all PL frames.',
            'One window per antenna does not establish repeatability.',
        ],
        'analysis_sources': [reference(Path(__file__).resolve()),
                             reference(ROOT / 'tools/analyze_antenna_comparison.py'),
                             reference(ROOT / 'tools/analyze_x1_board.py')],
    }
    write_evidence(output, result)
    print(json.dumps({'output': output.relative_to(ROOT).as_posix(),
                      'status': result['status'], 'observed_higher_role': better,
                      'runs': {key: value['metrics'] for key, value in records.items()}},
                     indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
