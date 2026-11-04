"""Read full timing summary, including hold endpoints, for isolated X1 builds."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    args = p.parse_args()
    directory = ROOT / 'build/reports' / ('cfar_x1_cluster_r%d' % args.attempt)
    output = directory / 'acceptance.json'
    if output.exists() or output.with_name(output.name + '.sha256').exists():
        raise FileExistsError('Preserve earlier acceptance')
    timing_path = directory / 'timing.rpt'
    timing = timing_path.read_text(encoding='utf-8')
    match = re.search(r'^\s*WNS\(ns\).*\n\s*-+.*\n\s*([^\r\n]+)', timing, re.M)
    if not match:
        raise ValueError('Missing complete timing summary')
    fields = match.group(1).split()
    if len(fields) != 12:
        raise ValueError('Unexpected timing summary layout')
    wns, tns, setup_failing, setup_total, whs, ths, hold_failing, hold_total, wpws, tpws, pulse_failing, pulse_total = map(float, fields)
    internal = (directory / 'internal_hold.rpt').read_text(encoding='utf-8')
    internal_match = re.search(r'Slack \((?:MET|VIOLATED)\)\s*:\s*(-?[\d.]+)ns', internal)
    if not internal_match:
        raise ValueError('Missing internal hold measurement')
    utilization = (directory / 'utilization.rpt').read_text(encoding='utf-8')
    resources = {}
    for label in ('Slice LUTs', 'Slice Registers', 'Block RAM Tile', 'DSPs'):
        entry = re.search(r'^\|\s*' + re.escape(label) + r'\s*\|\s*([\d.]+)\s*\|', utilization, re.M)
        if not entry:
            raise ValueError('Missing utilization row: ' + label)
        resources[label] = float(entry.group(1))
    passed = min(wns, whs, wpws) >= 0 and setup_failing == hold_failing == pulse_failing == 0
    result = {
        'status': 'PASS' if passed else 'FAIL',
        'recorded_at_pc': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'scope': 'Standalone cluster OOC with zero I/O delays; no board or whole-system timing acceptance',
        'clock_mhz': 150,
        'wns_ns': wns, 'whs_ns': whs, 'internal_hold_ns': float(internal_match.group(1)),
        'wpws_ns': wpws, 'setup_failing_endpoints': int(setup_failing),
        'hold_failing_endpoints': int(hold_failing), 'pulse_failing_endpoints': int(pulse_failing),
        'resources': resources,
        'limitations': [
            'OOC reports warn that clock location and boundary port routes are not fully specified.',
            'Boundary hold violations must not be hidden by passing internal-register hold alone.',
            'Integrated design must be rebuilt with actual clocks and inter-module paths.',
        ],
        'report_sha256': {path.name: sha(path) for path in sorted(directory.iterdir()) if path.is_file()},
    }
    if args.attempt == 1:
        result['original_script_marker_overridden'] = 'Original PASS only checked setup/internal hold; this full-report verdict supersedes it.'
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    output.with_name(output.name + '.sha256').write_text(sha(output) + '  ' + output.name + '\n', encoding='ascii')
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
