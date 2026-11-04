"""Preserve the first failed Z2 checkpoint link, without changing its inputs."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import zipfile

from x2_transport import ROOT, sha, write_evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempt', type=int, choices=(1, 2), required=True)
    parser.add_argument('--pid', type=int, required=True)
    args = parser.parse_args()
    tag = 'z2_link_failure_%d' % args.attempt
    archive_path = ROOT / ('report/results/' + tag + '.zip')
    result_path = ROOT / ('board/measurements/' + tag + '.json')
    if archive_path.exists() or result_path.exists():
        raise FileExistsError('Preserve existing link evidence')
    tcl = 'build/scripts/link_z2_recovery.tcl' if args.attempt == 1 else 'build/scripts/link_z2_nonproject.tcl'
    prefix = 'Y2_z2_link_r2' if args.attempt == 1 else 'Y2_z2_link_attempt2'
    names = [tcl, 'hs_err_pid%d.log' % args.pid, 'hs_err_pid%d.dmp' % args.pid,
             'tools/archive_z2_link.py']
    names += [p.relative_to(ROOT).as_posix() for p in
              sorted((ROOT / 'logs').glob(prefix + '*')) if p.is_file()]
    hashes = {name: sha(ROOT / name) for name in names}
    with zipfile.ZipFile(archive_path, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.write(ROOT / name, name)
        archive.writestr('MANIFEST.json', json.dumps(hashes, indent=2) + '\n')
    with zipfile.ZipFile(archive_path) as archive:
        for name, digest in hashes.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError('Archive mismatch: ' + name)
    digest = sha(archive_path)
    archive_path.with_name(archive_path.name + '.sha256').write_text(
        digest + '  ' + archive_path.name + '\n', encoding='ascii')
    write_evidence(result_path, dict(
        status='FAIL_CHECKPOINT_LINK', recorded_at_pc=datetime.now(timezone.utc).isoformat(),
        process_exit_code=int((ROOT / ('logs/' + prefix + '_exit.txt')).read_text().strip()),
        synthesis_invoked=False,
        diagnosis=('Vivado EXCEPTION_BREAKPOINT during project checkpoint open; cause undetermined' if args.attempt == 1
                   else 'Vivado EXCEPTION_ACCESS_VIOLATION while inserting adc_tap OOC checkpoint; cause undetermined'),
        evidence_marker=('TclStackFree: incorrect freePtr' if args.attempt == 1
                         else 'Abnormal program termination (EXCEPTION_ACCESS_VIOLATION)'),
        board_loaded=False, archive=archive_path.relative_to(ROOT).as_posix(),
        archive_sha256=digest, files_sha256=hashes))
    print('Z2_LINK_FAILURE_ARCHIVED files=%d' % len(hashes))


if __name__ == '__main__':
    main()
