"""Archive the completed three-round X1 checkpoint without promoting failures.

Read-only verification of existing evidence; never connects to the board.
The output is write-once. A FAIL is an archived result, not script failure.
"""
from datetime import datetime
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'board/measurements/x1_acceptance_summary.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_verified(relative, evidence):
    path = ROOT / relative
    digest = sha(path)
    if Path(str(path) + '.sha256').read_text().split()[0] != digest:
        raise ValueError('SHA256 mismatch: ' + relative)
    evidence.append({'path': relative, 'sha256': digest})
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    if OUTPUT.exists() or Path(str(OUTPUT) + '.sha256').exists():
        raise FileExistsError('Preserve archived checkpoint')
    evidence = []
    audit = read_verified('board/overlay/sentinel_v1b/acceptance.json', evidence)
    for name, digest in audit['artifacts_sha256'].items():
        if sha(ROOT / 'board/overlay/sentinel_v1b' / name) != digest:
            raise ValueError('Artifact changed: ' + name)
    for name, digest in audit['report_sha256'].items():
        if sha(ROOT / 'build/reports/sentinel_v1b' / name) != digest:
            raise ValueError('Routed report changed: ' + name)
    for name, field in [('docs/x1_v1b_prebuild_r2.json', 'sources_sha256'),
                        ('docs/x1_software_predeployment_r3.json', 'source_sha256')]:
        manifest = read_verified(name, evidence)
        for relative, digest in manifest[field].items():
            if sha(ROOT / relative) != digest:
                raise ValueError('Frozen input changed: ' + relative)
    checks = {}
    for label, relative in [
        ('core', 'sim/results/x1_core_r3_acceptance.json'),
        ('chain', 'sim/results/x1_chain_r2_acceptance.json'),
        ('deployment', 'board/measurements/x1_deployment_r1.json'),
        ('selftest', 'board/measurements/x1_selftest_r1_acceptance.json'),
        ('visual_r1_only', 'board/measurements/x1_visual_r1.json'),
        ('postflight', 'board/measurements/x1_postflight_r3.json'),
    ]:
        checks[label] = read_verified(relative, evidence)
    boot = checks['postflight']['boot_id']
    rounds = []
    for attempt in (1, 2, 3):
        metric = read_verified('board/measurements/x1_rf_metrics_r%d.json' % attempt, evidence)
        for mode in ('capacity', 'station'):
            name = 'board/measurements/x1_%s_r%d.json' % (mode, attempt)
            measurement = read_verified(name, evidence)
            receipt = read_verified(name.removesuffix('.json') + '_execution.json', evidence)
            if (receipt['status'] != 'PASS_EXECUTION' or receipt['result_sha256'] != sha(ROOT / name)
                    or measurement['boot_id'] != boot or receipt['boot_id_before'] != boot
                    or receipt['boot_id_after'] != boot
                    or measurement['artifacts_sha256'] != audit['artifacts_sha256']
                    or metric['evidence'][mode]['sha256'] != sha(ROOT / name)):
                raise ValueError('RF execution/provenance mismatch: ' + name)
        rounds.append({'attempt': attempt, 'status': metric['status'], 'metrics': metric['x1']})
    if audit['status'] != 'PASS' or checks['postflight']['status'] != 'PASS':
        raise ValueError('Hardware audit or stop state failed')
    if any(item['status'] != 'FAIL_METRICS' for item in rounds):
        raise ValueError('This checkpoint expects three failed RF rounds; reassess acceptance explicitly')
    result = {
        'status': 'FAIL', 'step': 'X1',
        'recorded_at_pc': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'reason': 'Three RF rounds did not jointly meet capacity <5% and station detection >=80%',
        'scope': 'Implementation/selftest passed; X1 RF quality acceptance failed',
        'attempt_limit_reached': True, 'X2_started': False, 'boot_id': boot,
        'artifacts_sha256': audit['artifacts_sha256'], 'rounds': rounds,
        'visual_scope': 'User accepted r1 display/frequency only; not final r3 RF metrics',
        'postflight': checks['postflight'], 'evidence': evidence,
        'next_decision': 'docs/x1_next_decision.md',
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    Path(str(OUTPUT) + '.sha256').write_text(sha(OUTPUT) + '  ' + OUTPUT.name + '\n', encoding='ascii')
    print(json.dumps({'status': result['status'], 'verified_evidence_files': len(evidence),
                      'output': OUTPUT.relative_to(ROOT).as_posix()}, indent=2))


if __name__ == '__main__':
    main()
