"""Save new/changed workspace content against a verified full snapshot.

The result requires the named full snapshot for restoration. No source files
are deleted. Exclusions are identical to make_handoff_zip; Git ignore rules
do not exclude measured IQ, session data or local transfer archives.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

from make_handoff_zip import CHUNK, MANIFEST, digest, git_revision, snapshot_files

INCREMENTAL_MANIFEST = 'zss/INCREMENTAL_MANIFEST.json'


def safe_path(name):
    parts = PurePosixPath(name).parts
    if (not parts or '..' in parts or '\\' in name or ':' in name
            or PurePosixPath(name).is_absolute()):
        raise ValueError('Unsafe snapshot path: ' + name)
    return name


def verify_incremental(path):
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read(INCREMENTAL_MANIFEST))
        names = archive.namelist()
        expected = {INCREMENTAL_MANIFEST}
        for item in manifest['files']:
            name = 'zss/' + safe_path(item['path'])
            if name in expected:
                raise ValueError('Duplicate manifest path')
            expected.add(name)
            count, h = 0, hashlib.sha256()
            with archive.open(name) as stream:
                for chunk in iter(lambda: stream.read(CHUNK), b''):
                    count += len(chunk)
                    h.update(chunk)
            if count != item['bytes'] or h.hexdigest() != item['sha256']:
                raise ValueError('Payload integrity mismatch: ' + name)
        if len(names) != len(set(names)) or set(names) != expected:
            raise ValueError('Unexpected archive member')
        return manifest


def create_incremental(root, base, output):
    root, base, output = root.resolve(), base.resolve(), output.resolve()
    partial = output.with_suffix(output.suffix + '.partial')
    if any(p.exists() for p in (output, partial, Path(str(output)+'.sha256'),
                               Path(str(output)+'.json'))):
        raise FileExistsError('Refusing to overwrite incremental snapshot')
    base_hash = digest(base)
    if Path(str(base)+'.sha256').read_text().split()[0] != base_hash:
        raise ValueError('Full snapshot hash mismatch')
    with zipfile.ZipFile(base) as archive:
        items = json.loads(archive.read(MANIFEST))['files']
    baseline = {safe_path(x['path']): x for x in items}
    if len(baseline) != len(items):
        raise ValueError('Duplicate baseline path')
    output.parent.mkdir(parents=True, exist_ok=True)
    entries, current = [], set()
    with zipfile.ZipFile(partial, 'x', allowZip64=True) as archive:
        for path, relative in snapshot_files(root):
            if path.resolve() in (output, partial):
                continue
            current.add(relative)
            before = path.stat()
            old = baseline.get(relative)
            if old and old['bytes'] == before.st_size and digest(path) == old['sha256']:
                after = path.stat()
                if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
                    raise RuntimeError('File changed during comparison: '+relative)
                continue
            info = zipfile.ZipInfo.from_file(path, 'zss/'+safe_path(relative))
            info.compress_type = (zipfile.ZIP_STORED if path.suffix in {'.npz', '.zip', '.gz', '.xsa'}
                                  or before.st_size > 32*CHUNK else zipfile.ZIP_DEFLATED)
            h, count = hashlib.sha256(), 0
            with path.open('rb') as source, archive.open(info, 'w', force_zip64=True) as target:
                for chunk in iter(lambda: source.read(CHUNK), b''):
                    target.write(chunk)
                    h.update(chunk)
                    count += len(chunk)
            after = path.stat()
            if count != before.st_size or after.st_mtime_ns != before.st_mtime_ns or after.st_size != count:
                raise RuntimeError('File changed during snapshot: '+relative)
            entries.append(dict(path=relative, bytes=count, sha256=h.hexdigest()))
            if len(entries) % 1000 == 0:
                print('Packed %d changed/new files' % len(entries), flush=True)
        manifest = dict(schema='incremental_snapshot/1', base_archive=base.name,
                        base_sha256=base_hash, git_head=git_revision(root), files=entries,
                        absent_from_workspace=sorted(set(baseline)-current),
                        restore='Extract full snapshot into a new folder, then overlay this ZIP. '
                                'Absent paths are informational; no automatic deletion. '
                                'No Git history, virtualenv, logs, SD images or Vivado DCP.')
        archive.writestr(INCREMENTAL_MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2),
                         compress_type=zipfile.ZIP_DEFLATED)
    checked = verify_incremental(partial)
    if checked != manifest:
        raise ValueError('Manifest verification failed')
    partial.rename(output)
    receipt = dict(schema='incremental_snapshot_receipt/1', archive=output.name,
                   sha256=digest(output), bytes=output.stat().st_size,
                   file_count=len(entries), uncompressed_bytes=sum(x['bytes'] for x in entries),
                   base_archive=base.name, base_sha256=base_hash,
                   all_payload_hashes_verified=True, git_head=manifest['git_head'])
    Path(str(output)+'.sha256').write_text(receipt['sha256']+'  '+output.name+'\n')
    Path(str(output)+'.json').write_text(json.dumps(receipt, indent=2)+'\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(create_incremental(Path(__file__).resolve().parents[1], args.base, args.output),
                     indent=2), flush=True)
