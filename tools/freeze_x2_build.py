"""Freeze/verify X2 implementation inputs without replacing prior evidence."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified(path):
    if sha(path) != Path(str(path)+'.sha256').read_text().split()[0]:
        raise ValueError('Evidence digest mismatch: '+str(path))
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    output = ROOT/('docs/x2_v1c_prebuild_r%d.json' % args.attempt)
    if args.verify:
        evidence = verified(output)
        for name, digest in evidence['sources_sha256'].items():
            if sha(ROOT/name) != digest:
                raise ValueError('Frozen build input changed: '+name)
        print('X2_PREBUILD_VERIFIED')
        return
    if output.exists() or Path(str(output)+'.sha256').exists():
        raise FileExistsError(output)
    simulation_path = ROOT/'sim/results/x2_simulation_acceptance.json'
    simulation = verified(simulation_path)
    if simulation['status'] != 'PASS':
        raise ValueError('Simulation must pass before implementation')
    for field in ('source_sha256', 'log_sha256'):
        for name, digest in simulation[field].items():
            if sha(ROOT/name) != digest:
                raise ValueError('Simulation evidence changed: '+name)
    inputs = {ROOT/name for name in simulation['source_sha256']}
    inputs |= set((ROOT/'src/hw/sentinel_v1c').rglob('*'))
    inputs |= set((ROOT/'src/constraints').rglob('*'))
    for folder in ('x2_packaged_ip', 'x1_packaged_ip', 'packaged_ip_round2',
                   'n3_packaged_ip_round2', 'n4_packaged_ip_round2'):
        directory = ROOT/'build/work'/folder
        if not directory.is_dir():
            raise FileNotFoundError(directory)
        inputs |= {p for p in directory.rglob('*') if p.is_file() and
                   (p.suffix.lower() in ('.v', '.sv', '.vhd', '.hex', '.xci', '.xdc', '.tcl')
                    or p.name == 'component.xml')}
    inputs |= {ROOT/name for name in ('tools/freeze_x2_build.py', 'tools/build_sentinel_v1c.ps1',
        'tools/audit_sentinel_v1c.ps1', 'tools/accept_sentinel_v1c.py',
        'tools/sync_hw.ps1', 'tools/collect_hw.ps1', 'build/scripts/package_x2.tcl',
        'build/scripts/audit_sentinel_v1c.tcl', 'sim/results/x2_simulation_acceptance.json')}
    if args.attempt > 1:
        inputs |= {ROOT/name for name in ('tools/retry_x2_implementation.ps1',
            'build/scripts/retry_x2_implementation.tcl', 'docs/x2_implementation_r1_failure.json')}
    result = dict(status='READY_FOR_IMPLEMENTATION', attempt=args.attempt,
                  recorded_at_pc=datetime.now(timezone.utc).isoformat(),
                  scope='Source freeze only; no routed or board acceptance',
                  sources_sha256={p.relative_to(ROOT).as_posix(): sha(p)
                                  for p in sorted(inputs) if p.is_file()})
    output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    Path(str(output)+'.sha256').write_text(sha(output)+'  '+output.name+'\n', encoding='ascii')
    print('X2_PREBUILD_FROZEN inputs='+str(len(result['sources_sha256'])))


if __name__ == '__main__':
    main()
