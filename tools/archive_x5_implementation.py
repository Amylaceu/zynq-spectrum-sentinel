"""Preserve X5 implementation evidence without replacing original manifests."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, required=True, choices=(1, 2, 3))
    args = parser.parse_args()
    project = ROOT/'build/work/adi_hdl/projects/fmcomms2/sentinel_v1d'
    output = ROOT/('report/results/x5_implementation_r%d.zip' % args.attempt)
    summary = ROOT/('board/measurements/x5_implementation_r%d.json' % args.attempt)
    if output.exists() or summary.exists():
        raise FileExistsError('Preserve existing implementation archive')
    files = {p for p in project.rglob('*') if p.is_file() and
             (p.suffix in ('.rpt', '.txt', '.log', '.tcl', '.xdc', '.xpr', '.bd') or
              p.name in ('system_top_postroute_physopt.dcp', 'system_top_routed.dcp',
                         'system_top_bad_timing.xsa'))}
    files.update(p for p in (ROOT/'logs').glob('X5_v1d*') if p.is_file())
    files.update(p for p in (ROOT/'logs').glob('X5_final_audit*') if p.is_file())
    files.update(p for p in (ROOT/'build/reports/sentinel_v1d').glob('*') if p.is_file())
    files.update(p for p in (ROOT/'board/overlay/sentinel_v1d').glob('*') if p.is_file())
    files.update(p for p in (ROOT/'docs').glob('x5_v1d_prebuild_r%d.json*' % args.attempt))
    manifest = {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(files)}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
        for name in manifest:
            archive.write(ROOT/name, name)
        archive.writestr('MANIFEST.json', json.dumps(manifest, indent=2)+'\n')
    with zipfile.ZipFile(output) as archive:
        for name, digest in manifest.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError('Archive verification failed: '+name)
    value = dict(schema='x5-implementation-archive-v1', attempt=args.attempt,
                 recorded_at_pc=datetime.now(timezone.utc).isoformat(),
                 archive=output.relative_to(ROOT).as_posix(), archive_sha256=sha(output),
                 files=len(manifest), status='ARCHIVED',
                 scope='Preserved implementation inputs/results; not a board acceptance',
                 sources_sha256=manifest)
    summary.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
    for path in (output, summary):
        Path(str(path)+'.sha256').write_text(sha(path)+'  '+path.name+'\n', encoding='ascii')
    print('X5_IMPLEMENTATION_ARCHIVED files=%d' % len(manifest))


if __name__ == '__main__':
    main()
