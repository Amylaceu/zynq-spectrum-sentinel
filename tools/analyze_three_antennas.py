"""Audit three receive-only antenna windows, preserving previous evidence.

No board operations are performed. Antenna identity and placement uncertainty
remain explicit; this comparison does not change X1 acceptance.
"""

import argparse
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from analyze_antenna_comparison import audit_run, read_verified, reference
from run_x1_board import ROOT, sha, write_evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path,
                        default=Path('board/measurements/antenna_comparison_three_r1.json'))
    args = parser.parse_args()
    output = (ROOT / args.out).resolve()
    if output.exists() or Path(str(output) + '.sha256').exists():
        parser.error('Preserve previous comparison evidence')

    names = ('long', 'short', 'third')
    runs = {}
    records = {}
    for name in names:
        path = ROOT / ('board/measurements/antenna_compare_%s_r1.json' % name)
        data, receipt, result = audit_run(path, name)
        runs[name] = (data, receipt)
        records[name] = result

    first, first_receipt = runs['long']
    for name in names[1:]:
        data, receipt = runs[name]
        for key in ('configuration', 'actual_lo_hz', 'actual_rate_hz',
                    'rf_bandwidth_hz', 'bus_phase', 'artifacts_sha256', 'boot_id'):
            if data[key] != first[key]:
                raise ValueError('Comparison inputs differ: %s: %s' % (name, key))
        if receipt['monitor_sha256'] != first_receipt['monitor_sha256']:
            raise ValueError('Monitor software differs: ' + name)
    for previous, current in zip(names, names[1:]):
        if (datetime.fromisoformat(records[previous]['ended_at_pc'])
                > datetime.fromisoformat(records[current]['started_at_pc'])):
            raise ValueError('Measurement windows overlap or are reversed')

    frozen_path = ROOT / 'docs/x1_software_predeployment_r3.json'
    frozen = read_verified(frozen_path)
    for relative, digest in frozen['source_sha256'].items():
        if sha(ROOT / relative) != digest:
            raise ValueError('Frozen software changed: ' + relative)
    previous_path = ROOT / 'board/measurements/antenna_comparison_r1.json'
    previous_result = read_verified(previous_path)
    for name in ('long', 'short'):
        if records[name]['metrics'] != previous_result['runs'][name]['metrics']:
            raise ValueError('Previously reported antenna metrics differ: ' + name)

    rates = {name: records[name]['metrics']['station_detection_rate_all_attempts']
             for name in names}
    ranked = sorted(names, key=lambda name: rates[name], reverse=True)
    best = [name for name in names if rates[name] == max(rates.values())]
    third_receipt = runs['third'][1]
    records['third']['identity_status'] = third_receipt['antenna_identification_status']
    records['third']['same_placement_explicitly_confirmed'] = (
        third_receipt['same_placement_explicitly_confirmed'])
    result = {
        'status': 'COMPLETED_THREE_ANTENNA_COMPARISON',
        'recorded_at_pc': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'scope': 'Three sequential 120s receive-only station windows; not full X1 acceptance',
        'station_hz': 95800000, 'tolerance_hz': 25000,
        'configuration': first['configuration'],
        'actual_lo_hz': first['actual_lo_hz'],
        'actual_rate_hz': first['actual_rate_hz'],
        'rf_bandwidth_hz': first['rf_bandwidth_hz'],
        'bus_phase': first['bus_phase'], 'boot_id': first['boot_id'],
        'artifacts_sha256': first['artifacts_sha256'],
        'monitor_sha256': first_receipt['monitor_sha256'],
        'frozen_software': reference(frozen_path),
        'frozen_software_files_verified': len(frozen['source_sha256']),
        'previous_two_antenna_summary': reference(previous_path),
        'runs': records, 'detection_rate_descending': ranked,
        'observed_highest_station_detection_antennas': best,
        'detection_percentage_point_differences': {
            '%s_minus_%s' % (a, b): (rates[a] - rates[b]) * 100
            for a, b in (('short', 'long'), ('third', 'long'), ('third', 'short'))
        },
        'human_confirmed_same_placement_all_three': False,
        'x1_acceptance_unchanged': 'FAIL; no additional 98MHz capacity window was measured',
        'limitations': [
            'Third antenna model and frequency range were not provided.',
            'Third antenna connection was confirmed; identical placement was not explicitly confirmed.',
            'Only the current placement and 95.8MHz station were compared; no full-band gain measurement.',
            'Sequential over-the-air runs can differ with time, multipath and contact quality.',
            'Receiver-reported RSSI is not calibrated target SNR or antenna gain.',
            'The denominator includes all scheduled telemetry attempts, not all PL frames.',
            'Only one run per antenna; the observed preference is provisional.',
        ],
        'analysis_sources': [reference(Path(__file__).resolve()),
                             reference(ROOT / 'tools/analyze_antenna_comparison.py'),
                             reference(ROOT / 'tools/analyze_x1_board.py')],
    }
    write_evidence(output, result)
    print(json.dumps({'output': output.relative_to(ROOT).as_posix(),
                      'status': result['status'], 'ranking': ranked,
                      'runs': {name: records[name]['metrics'] for name in names}},
                     indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
