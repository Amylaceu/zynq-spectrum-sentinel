"""Archive round-three core results after independently parsing routed reports."""
import hashlib
import json
import re
from pathlib import Path

from accept_sentinel_v1 import timing_summary

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    final = json.loads((ROOT / 'logs/X5_verification_final.json').read_text())
    if final['status'] != 'PASS':
        raise ValueError('Final core verification is not PASS')
    sources = final['sources'] + [final['shared_fft_read_only_snapshot']]
    logs = [entry for entry in final['simulation'].values()
            if isinstance(entry, dict) and 'required_marker' in entry]
    logs += [final['ooc']['run']] + final['ooc']['reports']
    for entry in sources + logs:
        if not entry['exists'] or sha(ROOT / entry['path']) != entry['sha256']:
            raise ValueError('Missing or changed evidence: ' + entry['path'])
        if 'required_marker' in entry:
            if entry['required_marker'] not in (ROOT / entry['path']).read_text(errors='replace'):
                raise ValueError('Missing PASS marker: ' + entry['path'])
    reports = ROOT / 'build/reports/x5_core/round3'
    timing = timing_summary((reports / 'routed_timing.rpt').read_text(errors='replace'))
    utilization_text = (reports / 'routed_utilization.rpt').read_text(errors='replace')
    match = re.search(r'^\| x5_channel_capture\s*\|\s*\(top\)\s*\|(.+)\|$',
                      utilization_text, re.MULTILINE)
    if not match:
        raise ValueError('Missing top-level hierarchical resource row')
    counts = [int(field.strip()) for field in match[1].split('|')]
    if len(counts) != 8:
        raise ValueError('Malformed resource row')
    resources = dict(lut=counts[0], ff=counts[4], ramb36=counts[5],
                     ramb18=counts[6], bram_tiles=counts[5]+counts[6]/2, dsp=counts[7])
    if resources != final['ooc']['resources'] | {'bram_tiles': 9.0}:
        raise ValueError('Resources differ from verification receipt')
    result = dict(final, final_timing_parsed=timing, resources_parsed=resources,
                  source_sha256={e['path']: e['sha256'] for e in sources},
                  log_sha256={e['path']: e['sha256'] for e in logs})
    result['source_sha256']['tools/accept_x5_core.py'] = sha(Path(__file__))
    path = ROOT / 'sim/results/x5_core_acceptance.json'
    if path.exists():
        raise FileExistsError('Preserve prior evidence: ' + str(path))
    path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    Path(str(path) + '.sha256').write_text(sha(path) + '  ' + path.name + '\n', encoding='ascii')
    print('X5_CORE_ACCEPTANCE_PASS', timing, resources)


if __name__ == '__main__':
    main()
