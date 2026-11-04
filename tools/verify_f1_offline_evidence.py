"""Audit frozen offline inputs and replay stored FM snapshots; never access hardware.

This is evidence checking and Python model replay, not a new RTL simulation or
board acceptance. Keep failed pytest attempts visible in the resulting JSON.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/ps'))
from sentinel.fm_quality import stereo_quality


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified(path):
    if sha(path) != Path(str(path) + '.sha256').read_text().split()[0]:
        raise ValueError('Evidence checksum mismatch: ' + str(path))
    return json.loads(path.read_text(encoding='utf-8'))


def audit():
    result = dict(scope='Offline numeric models and historical evidence only; no RF, SD, RTL build or board acceptance',
                  recorded_utc=datetime.now(timezone.utc).isoformat(),
                  git_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  source_sha256={}, pytest_attempts=[], fm_snapshots=[])
    def record(path):
        result['source_sha256'][path.relative_to(ROOT).as_posix()] = sha(path)
    record(Path(__file__))
    record(ROOT / 'src/ps/sentinel/fm_quality.py')
    manifest_path = ROOT / 'data/reference/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    record(manifest_path)
    for name, info in manifest['files'].items():
        path = manifest_path.parent / name
        if sha(path) != info['sha256'] or path.stat().st_size != info['size_bytes']:
            raise ValueError('Golden input mismatch: ' + name)
    result['golden_files_verified'] = len(manifest['files'])

    evidence_path = ROOT / 'sim/results/v2_cfar_r1.json'
    evidence = verified(evidence_path)
    record(evidence_path)
    for group in ('source_sha256', 'log_sha256'):
        for name, digest in evidence[group].items():
            path = ROOT / name
            if sha(path) != digest:
                raise ValueError('Historical CFAR evidence changed: ' + name)
            record(path)
    comparisons = {}
    for name in evidence['comparisons']:
        expected = ROOT / 'data/reference/cfar/x1_guard8' / (('targets_words' if name == 'targets' else name) + '.hex')
        actual = ROOT / ('sim/results/v2_cfar_' + name + '_out.hex')
        a = [int(x, 16) for x in expected.read_text().split()]
        b = [int(x, 16) for x in actual.read_text().split()]
        if not a or a != b:
            raise ValueError('Historical CFAR words differ: ' + name)
        comparisons[name] = dict(words=len(a), mismatches=0)
    result['historical_cfar'] = dict(cases=evidence['cases'], comparisons=comparisons,
                                     new_rtl_simulation=False)

    frozen_path = ROOT / 'board/measurements/y3_quality_frozen_snapshot_validation.json'
    frozen = verified(frozen_path)
    record(frozen_path)
    for item in frozen['captures']:
        path = ROOT / 'board/measurements' / item['run'] / item['file']
        if sha(path) != item['sha256']:
            raise ValueError('IQ checksum mismatch: ' + str(path))
        record(path)
        with np.load(path, allow_pickle=False) as data:
            metrics = stereo_quality(data['iq'])
        for key in ('pilot_frequency_hz', 'pilot_prominence_db', 'large_excursion_fraction', 'iq_rms'):
            if not np.isclose(metrics[key], item[key], rtol=1e-10, atol=1e-10):
                raise ValueError('Frozen metric changed: ' + key)
        if metrics['good'] != item['good']:
            raise ValueError('Frozen quality decision changed')
        result['fm_snapshots'].append(dict(file=path.relative_to(ROOT).as_posix(), **metrics,
            f1_quality_pass=bool(metrics['good'] and metrics['pilot_prominence_db'] >= 20)))

    replay_path = ROOT / 'sim/results/f1_frozen_iq_20261103/analysis.json'
    replay = verified(replay_path)
    record(replay_path)
    sigmf = ROOT / 'data/captured/fm_diagnostic/fm_95800000_round3.sigmf-data'
    meta_path = sigmf.with_suffix('.sigmf-meta')
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    raw = sigmf.read_bytes()
    if hashlib.sha512(raw).hexdigest() != meta['global']['core:sha512']:
        raise ValueError('Historical SigMF SHA512 mismatch')
    if sha(sigmf) != replay['historical_source_sha256'] or sha(meta_path) != replay['historical_meta_sha256']:
        raise ValueError('Historical IQ source differs from replay receipt')
    record(sigmf)
    record(meta_path)
    result['historical_iq_sigmf_sha512_verified'] = True
    for name, digest in replay['wav_sha256'].items():
        path = replay_path.parent / name
        if sha(path) != digest:
            raise ValueError('Replay WAV changed: ' + name)
        record(path)
    result['historical_iq_replay'] = replay['historical']
    attempts = sorted((ROOT / 'sim/results').glob('frozen_offline_regression_20261103*.xml'))
    if len(attempts) != 3:
        raise ValueError('Expected three preserved pytest attempts')
    for path in attempts:
        record(path)
        groups, failures = {}, []
        for case in ET.parse(path).getroot().iter('testcase'):
            module = case.get('classname', '')
            group = 'golden' if module.startswith('sim.') else 'ps' if module.startswith('src.') else 'tools'
            counts = groups.setdefault(group, dict(tests=0, failures=0, errors=0, skipped=0))
            counts['tests'] += 1
            for tag, key in (('failure', 'failures'), ('error', 'errors'), ('skipped', 'skipped')):
                child = case.find(tag)
                if child is not None:
                    counts[key] += 1
                    failures.append(dict(test=module + '::' + case.get('name', ''),
                                         kind=tag, message=child.get('message', '')))
        result['pytest_attempts'].append(dict(file=path.name, groups=groups, failures=failures))
    last = result['pytest_attempts'][-1]['groups']
    if any(last[g][k] for g in ('golden', 'ps') for k in ('failures', 'errors', 'skipped')):
        raise ValueError('Signal-processing/PS regression not passed')
    for path in sorted((ROOT / 'logs').glob('F1_frozen_offline_regression_20261103*.log')):
        record(path)
    record(ROOT / 'logs/F1_frozen_iq_20261103.log')
    # Full suite remains incomplete even though the signal-processing tests pass.
    result['status'] = 'OFFLINE_CHECKS_PASS_WITH_REGRESSION_ENV_ERRORS'
    result['f1_board_acceptance'] = 'NOT_RUN'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    sidecar = Path(str(args.out) + '.sha256')
    if args.out.exists() or sidecar.exists():
        raise FileExistsError('Preserve existing evidence')
    result = audit()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    sidecar.write_text(sha(args.out) + '  ' + args.out.name + '\n', encoding='ascii')
    print(json.dumps(dict(status=result['status'], golden_files=result['golden_files_verified'],
                         cfar=result['historical_cfar'], fm_snapshots=len(result['fm_snapshots']),
                         f1_quality_pass=sum(row['f1_quality_pass'] for row in result['fm_snapshots']))))


if __name__ == '__main__':
    main()
