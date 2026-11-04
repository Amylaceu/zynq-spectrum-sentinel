"""Independently compare archived X1 cluster simulation output to hashed vectors."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    args = p.parse_args()
    tag = 'r%d' % args.attempt
    vectors = ROOT / 'data/reference/cfar' / ('x1_' + tag)
    manifest_path = vectors / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if (vectors / 'manifest.json.sha256').read_text().split()[0] != sha(manifest_path):
        raise ValueError('Vector manifest hash mismatch')
    for name, expected in manifest['sha256'].items():
        if Path(name).name != name or sha(vectors / name) != expected:
            raise ValueError('Vector content/hash mismatch: ' + name)
    records = [int(x, 16) for x in (vectors / 'targets.hex').read_text().split()]
    stats = [int(x, 16) for x in (vectors / 'stats.hex').read_text().split()]
    cases = manifest['cases']
    if len(records) != len(cases) * 32 or len(stats) != len(cases) * 6:
        raise ValueError('Wrong vector lengths')
    expected = []
    for index, case in enumerate(cases):
        if stats[index * 6] != case['targets']:
            raise ValueError('Manifest count mismatch')
        expected.extend(records[index * 32:index * 32 + case['targets']])
    output = ROOT / 'logs' / ('X1_cluster_targets_' + tag + '.hex')
    actual = [int(x, 16) for x in output.read_text().split()]
    if actual != expected:
        raise ValueError('RTL records mismatch (including record count/order)')
    log = ROOT / 'logs' / ('X1_cluster_xsim_' + tag + '.log')
    text = log.read_text(encoding='utf-8-sig')
    marker = re.search(r'^TB_RESULT: PASS X1_CLUSTER cases=(\d+) records=(\d+) cycles=(\d+)', text, re.M)
    passed_cases = [int(x) for x in re.findall(r'^X1_CASE_PASS (\d+) ', text, re.M)]
    if not marker or tuple(map(int, marker.group(1, 2))) != (len(cases), len(actual)):
        raise ValueError('Missing/inconsistent simulation PASS marker')
    if passed_cases != list(range(len(cases))):
        raise ValueError('Case results missing or duplicated')
    files = ['sim/golden/cfar_x1.py', 'src/rtl/cfar_x1/cfar_cluster_x1.v',
             'sim/tb/tb_cfar_cluster_x1.sv', 'tools/export_cfar_x1_vectors.py']
    result = {'status': 'PASS', 'recorded_at_pc': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
              'scope': 'Standalone X1 cluster simulation, not integrated CFAR/bitstream/board acceptance',
              'cases': len(cases), 'input_bins': len(cases) * 2048,
              'compared_target_records': len(actual), 'record_bits': 128,
              'mismatches': 0, 'simulation_cycles_including_testbench': int(marker.group(3)),
              'manifest_sha256': sha(manifest_path), 'output_sha256': sha(output), 'log_sha256': sha(log),
              'source_sha256': {name: sha(ROOT / name) for name in files},
              'hardware_accessed': False, 'whole_system_timing_verified': False}
    path = ROOT / 'sim/results' / ('x1_cluster_' + tag + '_acceptance.json')
    if path.exists() or path.with_name(path.name + '.sha256').exists():
        raise FileExistsError('Preserve existing acceptance')
    path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    path.with_name(path.name + '.sha256').write_text(sha(path) + '  ' + path.name + '\n', encoding='ascii')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
