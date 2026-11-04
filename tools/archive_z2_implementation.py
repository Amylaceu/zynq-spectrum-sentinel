"""Archive a completed Z2 implementation attempt before recovery/rebuild."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

from x2_transport import ROOT, sha, verified, write_evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--note', required=True)
    args = parser.parse_args()
    tag = 'z2_implementation_r%d' % args.attempt
    destination = ROOT/('report/results/'+tag+'.zip')
    output = ROOT/('board/measurements/'+tag+'.json')
    if destination.exists() or output.exists():
        raise FileExistsError('Preserve implementation evidence')
    exitfile = ROOT/('logs/Y2_'+tag+'_exit.txt')
    code = exitfile.read_text(encoding='utf-8-sig').strip()
    if code not in ('0', '1'):
        raise ValueError('Implementation not finished')
    pre = ROOT/('docs/z2_prebuild_r%d.json' % args.attempt)
    manifest = verified(pre)
    files = {pre, pre.with_name(pre.name+'.sha256'), exitfile, Path(__file__)}
    for name, digest in manifest['sources_sha256'].items():
        path = ROOT/name
        if sha(path) != digest:
            raise ValueError('Frozen build input changed: '+name)
        files.add(path)
    suffixes = {'.tcl', '.v', '.sv', '.vhd', '.xdc', '.xci', '.xml', '.json',
                '.log', '.jou', '.rpt', '.dcp', '.vds', '.rst', '.bat', '.js',
                '.xpr', '.bd', '.hex', '.mif', '.bit', '.hwh', '.xsa', '.txt'}
    project = ROOT/'build/work/adi_hdl/projects/fmcomms2/sentinel_z2'
    files.update(p for p in project.rglob('*') if p.is_file() and p.suffix.lower() in suffixes)
    for folder in ('board/overlay/sentinel_z2', 'build/reports/sentinel_z2'):
        files.update(p for p in (ROOT/folder).rglob('*') if p.is_file())
    files.update(p for p in (ROOT/'logs').glob('Y2_z2*r%d*' % args.attempt) if p.is_file())
    hashes = {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(files)}
    with zipfile.ZipFile(destination, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name in hashes:
            archive.write(ROOT/name, name)
        archive.writestr('MANIFEST.json', json.dumps(hashes, indent=2)+'\n')
    with zipfile.ZipFile(destination) as archive:
        for name, digest in hashes.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError('Archive failed verification: '+name)
    destination.with_name(destination.name+'.sha256').write_text(
        sha(destination)+'  '+destination.name+'\n', encoding='ascii')
    write_evidence(output, dict(status='ARCHIVED', implementation_exit_code=int(code),
        attempt=args.attempt, note=args.note, recorded_at_pc=datetime.now(timezone.utc).isoformat(),
        scope='Preserved build inputs/outputs; not board acceptance',
        prebuild_sha256=sha(pre), file_count=len(hashes),
        archive=destination.relative_to(ROOT).as_posix(), archive_sha256=sha(destination)))
    print('Z2_IMPLEMENTATION_ARCHIVE_VERIFIED files=%d' % len(hashes))


if __name__ == '__main__':
    main()
