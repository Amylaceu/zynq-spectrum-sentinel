"""Freeze independent Z2 UI integration against the accepted v1d-r2 hardware."""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from x2_transport import ROOT, sha, verified, write_evidence
from x5_runtime_patch import hardware_base


def verify(attempt):
    path = ROOT/('docs/z2_prebuild_r%d.json' % attempt)
    value = verified(path)
    for name, digest in value['sources_sha256'].items():
        if sha(ROOT/name) != digest:
            raise ValueError('Frozen Z2 input changed: '+name)
    return path, value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify:
        verify(args.attempt)
        print('Z2_PREBUILD_VERIFIED')
        return
    base_path, accepted_path, _ = hardware_base(2)
    base = verified(base_path)
    evidence_path = ROOT/('sim/results/z2_pc_r%d.json' % args.attempt)
    evidence = verified(evidence_path)
    if evidence['status'] != 'PASS':
        raise ValueError('Z2 component evidence not passing')
    for field in ('source_sha256', 'log_sha256'):
        for name, digest in evidence[field].items():
            if sha(ROOT/name) != digest:
                raise ValueError('Z2 simulation/packaging evidence changed: '+name)
    sources = {ROOT/name for name in base['sources_sha256'] if name != 'src/ps/sentinel/v1d.py'}
    for folder in ('src/hw/sentinel_z2', 'src/rtl/lcd_z2', 'build/work/z2_packaged_ip'):
        sources.update(p for p in (ROOT/folder).rglob('*') if p.is_file() and
                       p.suffix in ('.v', '.xdc', '.tcl', '.xml'))
    sources.update(ROOT/name for name in evidence['source_sha256'])
    sources.update(ROOT/name for name in (
        'tools/build_sentinel_z2.ps1', 'tools/accept_sentinel_z2.py',
        'tools/audit_sentinel_z2.ps1', 'build/scripts/audit_sentinel_z2.tcl',
        'tools/freeze_z2_build.py'))
    sources.update((base_path, accepted_path, evidence_path))
    log = ROOT/('logs/Y2_z2_validate_r%d_controller.log' % args.attempt)
    if 'SENTINEL_BD_VALIDATION_PASS' not in log.read_text(errors='replace'):
        raise ValueError('Require independent Z2 BD validation')
    sources.add(log)
    value = dict(status='READY_FOR_IMPLEMENTATION', attempt=args.attempt,
                 recorded_at_pc=datetime.now(timezone.utc).isoformat(),
                 scope='Z2 UI revision; preserves prior v1d-r2 and Y2 station FAIL results; no board claim',
                 original_hardware_prebuild_sha256=sha(base_path),
                 original_hardware_acceptance_sha256=sha(accepted_path),
                 excluded_historical_ps_only=['src/ps/sentinel/v1d.py'],
                 sources_sha256={p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(sources)})
    path = ROOT/('docs/z2_prebuild_r%d.json' % args.attempt)
    write_evidence(path, value)
    verify(args.attempt)
    print('Z2_PREBUILD_FROZEN inputs=%d' % len(sources))


if __name__ == '__main__':
    main()
