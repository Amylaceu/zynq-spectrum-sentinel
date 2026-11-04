"""Audit two fixed-parameter antenna windows without running board operations.

Preserve raw measurements and X1 acceptance history. Detection uses every
scheduled telemetry attempt, including missing snapshots in the denominator.
"""

import argparse
from datetime import datetime
import json
from pathlib import Path
import statistics
from zoneinfo import ZoneInfo

from analyze_x1_board import sha, summarize
from run_x1_board import ROOT, write_evidence


def read_verified(path):
    """Read one local JSON evidence file only after checking its sidecar."""
    digest = sha(path)
    if digest != Path(str(path) + '.sha256').read_text().split()[0]:
        raise ValueError('Evidence hash mismatch: ' + str(path))
    return json.loads(path.read_text(encoding='utf-8-sig'))


def reference(path):
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path)}


def audit_run(path, antenna):
    data = read_verified(path)
    receipt_path = path.with_name(path.stem + '_execution.json')
    receipt = read_verified(receipt_path)
    if (receipt['status'] != 'PASS_EXECUTION' or receipt['ssh_exit_code'] != 0
            or receipt['antenna'] != antenna
            or receipt['user_confirmed_rx1a_tx_empty'] is not True
            or receipt['result_sha256'] != sha(path)
            or data['source'] != 'rf' or data['duration_requested_s'] != 120):
        raise ValueError('Incomplete or mislabeled execution: ' + str(path))
    for key in ('preflight', 'postflight'):
        state = receipt[key]
        if (state['status'] != 'PASS' or state['gpio_data'] != 0
                or state['source_ctrl'] != 0
                or state['boot_id'] != data['boot_id']):
            raise ValueError('Invalid receiver stop state: ' + key)
    if receipt['boot_id_before'] != data['boot_id']:
        raise ValueError('Board rebooted during a measurement')
    log = ROOT / receipt['log']
    if sha(log) != receipt['log_sha256']:
        raise ValueError('Execution log hash mismatch')
    for name, digest in data['artifacts_sha256'].items():
        if Path(name).name != name:
            raise ValueError('Artifact name must be a basename')
        if sha(ROOT / 'board/overlay/sentinel_v1b' / name) != digest:
            raise ValueError('Local hardware artifact changed: ' + name)
    if sha(ROOT / 'src/ps/sentinel/app/monitor_x1.py') != receipt['monitor_sha256']:
        raise ValueError('Frozen monitor source changed')
    metrics = summarize(data, 96400000)
    rssis = [row['rx_rssi_dbm'] for row in data['samples']]
    metrics['receiver_rssi_dbm'] = {
        'median': statistics.median(rssis), 'minimum': min(rssis),
        'maximum': max(rssis),
    }
    return data, receipt, {
        'antenna': antenna, 'description': receipt['antenna_description'],
        'metrics': metrics, 'elapsed_total_s': data['elapsed_total_s'],
        'started_at_pc': receipt['started_at_pc'],
        'ended_at_pc': receipt['ended_at_pc'],
        'evidence': {'measurement': reference(path),
                     'execution': reference(receipt_path), 'log': reference(log)},
        'receiver_stopped': True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--long', type=Path,
                        default=Path('board/measurements/antenna_compare_long_r1.json'))
    parser.add_argument('--short', type=Path,
                        default=Path('board/measurements/antenna_compare_short_r1.json'))
    parser.add_argument('--out', type=Path,
                        default=Path('board/measurements/antenna_comparison_r1.json'))
    args = parser.parse_args()
    output = (ROOT / args.out).resolve()
    if output.exists() or Path(str(output) + '.sha256').exists():
        parser.error('Preserve previous comparison evidence')
    runs = {}
    records = {}
    for name, path in [('long', args.long), ('short', args.short)]:
        data, receipt, result = audit_run((ROOT / path).resolve(), name)
        runs[name] = (data, receipt)
        records[name] = result
    first, second = runs['long'][0], runs['short'][0]
    for key in ('configuration', 'actual_lo_hz', 'actual_rate_hz',
                'rf_bandwidth_hz', 'bus_phase', 'artifacts_sha256', 'boot_id'):
        if first[key] != second[key]:
            raise ValueError('Comparison inputs differ: ' + key)
    if runs['long'][1]['monitor_sha256'] != runs['short'][1]['monitor_sha256']:
        raise ValueError('The two runs used different monitor software')
    if (datetime.fromisoformat(records['long']['ended_at_pc'])
            > datetime.fromisoformat(records['short']['started_at_pc'])):
        raise ValueError('Antenna measurement windows overlap or are reversed')
    frozen_path = ROOT / 'docs/x1_software_predeployment_r3.json'
    frozen = read_verified(frozen_path)
    for relative, digest in frozen['source_sha256'].items():
        if sha(ROOT / relative) != digest:
            raise ValueError('Frozen software changed: ' + relative)
    long_metrics = records['long']['metrics']
    short_metrics = records['short']['metrics']
    delta = (short_metrics['station_detection_rate_all_attempts']
             - long_metrics['station_detection_rate_all_attempts'])
    observed_better = 'short' if delta > 0 else 'long' if delta < 0 else None
    result = {
        'status': 'COMPLETED_ANTENNA_COMPARISON',
        'recorded_at_pc': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'scope': 'Two user-authorized 120s receive-only station windows; not full X1 acceptance',
        'station_hz': 95800000, 'tolerance_hz': 25000,
        'configuration': first['configuration'],
        'actual_lo_hz': first['actual_lo_hz'],
        'actual_rate_hz': first['actual_rate_hz'],
        'rf_bandwidth_hz': first['rf_bandwidth_hz'],
        'bus_phase': first['bus_phase'], 'boot_id': first['boot_id'],
        'artifacts_sha256': first['artifacts_sha256'],
        'monitor_sha256': runs['long'][1]['monitor_sha256'],
        'frozen_software': reference(frozen_path),
        'frozen_software_files_verified': len(frozen['source_sha256']),
        'human_confirmed_same_placement': True,
        'runs': records,
        'short_minus_long_detection_percentage_points': delta * 100,
        'observed_higher_station_detection_antenna': observed_better,
        'x1_acceptance_unchanged': 'FAIL; the 98MHz capacity window is not part of this comparison',
        'limitations': [
            'Only the current placement and 95.8MHz station were compared; no full-band gain measurement.',
            'Sequential over-the-air runs can differ with time, multipath and contact quality.',
            'Receiver-reported RSSI is not calibrated target SNR or antenna gain; AGC and other signals affect it.',
            'The denominator includes all scheduled telemetry attempts; snapshots are not independent PL frames.',
            'Only one run per antenna; the observed preference is provisional, not a repeatability result.',
        ],
        'analysis_sources': [reference(Path(__file__).resolve()),
                             reference(ROOT / 'tools/analyze_x1_board.py')],
    }
    write_evidence(output, result)
    print(json.dumps({'output': output.relative_to(ROOT).as_posix(),
                      'status': result['status'], 'observed_better': observed_better,
                      'runs': {key: value['metrics'] for key, value in records.items()}},
                     indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
