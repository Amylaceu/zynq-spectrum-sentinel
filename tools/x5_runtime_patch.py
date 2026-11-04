"""Bind PS-only revisions to an immutable, accepted X5 hardware build.

This records deployment compatibility fixes, never a new RTL simulation or
implementation attempt. Historical prebuild manifests are not rewritten.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from x2_transport import ROOT, sha, verified, write_evidence

ALLOWED_FROZEN_CHANGES = {'src/ps/sentinel/v1d.py'}


def hardware_base(attempt):
    path = ROOT/('docs/x5_v1d_prebuild_r%d.json' % attempt)
    base = verified(path)
    acceptance_path = ROOT/'board/overlay/sentinel_v1d/acceptance.json'
    acceptance = verified(acceptance_path)
    if (acceptance['status'] != 'PASS' or acceptance['image'] != 'sentinel_v1d'
            or acceptance['prebuild_manifest_sha256'] != sha(path)):
        raise ValueError('Hardware acceptance does not match original frozen build')
    changes = {}
    for name, digest in base['sources_sha256'].items():
        current = sha(ROOT/name)
        if current != digest:
            if name not in ALLOWED_FROZEN_CHANGES:
                raise ValueError('Hardware/simulation input changed: '+name)
            changes[name] = dict(original_sha256=digest, runtime_sha256=current)
    for name, digest in acceptance['artifacts_sha256'].items():
        if sha(acceptance_path.parent/name) != digest:
            raise ValueError('Accepted hardware artifact changed: '+name)
    return path, acceptance_path, changes


def runtime_sources():
    paths = set((ROOT/'src/ps/sentinel').rglob('*.py'))
    paths.update(ROOT/name for name in (
        'tools/run_x5_board.py', 'tools/x5_runtime_patch.py',
        'board/scripts/run_x5_monitor.py', 'board/scripts/x5_postflight.py',
        'src/ps/models/weights/amc_v2/round_3/model.npz'))
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(paths)}


def check_runtime_patch(path, attempt):
    value = verified(path)
    original, accepted, changes = hardware_base(attempt)
    if (value.get('schema') != 'x5-ps-runtime-patch-v1'
            or value['hardware_implementation_attempt'] != attempt
            or value['base_prebuild_sha256'] != sha(original)
            or value['hardware_acceptance_sha256'] != sha(accepted)
            or value['allowed_frozen_changes'] != changes
            or value['runtime_source_sha256'] != runtime_sources()):
        raise ValueError('Runtime patch does not match current source/hardware')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--implementation-attempt', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify:
        check_runtime_patch(args.output, args.implementation_attempt)
        print('X5_RUNTIME_PATCH_VERIFIED')
        return
    path, accepted, changes = hardware_base(args.implementation_attempt)
    value = dict(schema='x5-ps-runtime-patch-v1',
                 recorded_at_pc=datetime.now(timezone.utc).isoformat(),
                 scope='PS deployment fixes only; no new RTL simulation or implementation acceptance',
                 hardware_implementation_attempt=args.implementation_attempt,
                 base_prebuild_sha256=sha(path), hardware_acceptance_sha256=sha(accepted),
                 allowed_frozen_changes=changes, runtime_source_sha256=runtime_sources())
    write_evidence(args.output, value)
    check_runtime_patch(args.output, args.implementation_attempt)
    print('X5_RUNTIME_PATCH_CREATED')


if __name__ == '__main__':
    main()
