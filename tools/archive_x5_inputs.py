"""Archive frozen X5 inputs and their complete simulation evidence for handoff."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

from freeze_x5_build import ROOT, sha, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    args = parser.parse_args()
    frozen_path, frozen = verify(args.attempt)
    output = ROOT/('report/results/x5_inputs_r%d.zip' % args.attempt)
    summary = ROOT/('board/measurements/x5_checkpoint_r%d.json' % args.attempt)
    if output.exists() or summary.exists():
        raise FileExistsError('Preserve prior checkpoint')
    names = set(frozen['sources_sha256'])
    names.add(frozen_path.relative_to(ROOT).as_posix())
    for name in list(names):
        path = ROOT/name
        if Path(str(path)+'.sha256').is_file():
            names.add(name+'.sha256')
    manifest = {name: sha(ROOT/name) for name in sorted(names)}
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in manifest:
            archive.write(ROOT/name, name)
        archive.writestr('MANIFEST.json', json.dumps(manifest, indent=2)+'\n')
    with zipfile.ZipFile(output) as archive:
        for name, digest in manifest.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError('Archive entry mismatch '+name)
    value = dict(schema='x5-frozen-input-checkpoint-v1', attempt=args.attempt,
                 status='PASS_ARCHIVE', recorded_at_pc=datetime.now(timezone.utc).isoformat(),
                 scope='Inputs and PC evidence only; implementation and board acceptance pending',
                 archive=output.relative_to(ROOT).as_posix(), archive_sha256=sha(output),
                 files=len(manifest), files_sha256=manifest,
                 restore='Extract only to a new checkout or compare each file first; never blindly overwrite newer work')
    summary.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
    for path in (output, summary):
        Path(str(path)+'.sha256').write_text(sha(path)+'  '+path.name+'\n', encoding='ascii')
    print('X5_INPUTS_ARCHIVED files=%d' % len(manifest))


if __name__ == '__main__':
    main()
