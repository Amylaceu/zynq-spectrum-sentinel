"""Create a portable, hashed workspace snapshot, or verify/extract one.

No Git metadata, virtual environments, build work areas or SD images are copied.
Git-ignored vendor material, measurements, model weights and datasets ARE copied.
The archive is a source/data snapshot, not a Vivado incremental-build checkpoint.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

CHUNK = 1024 * 1024
SKIP_DIRS = {'.git', '.venv', '__pycache__', '.pytest_cache', '.Xil',
             '.ipynb_checkpoints'}
SKIP_SUFFIXES = ('.cache', '.runs', '.hw', '.ip_user_files', '.sim', '.gen')
SKIP_PREFIXES = ('dist/', 'logs/', 'build/work/', 'build/sd_boot_backup/',
                 'build/sd_reference/', 'build/sim_lcd/')
SKIP_FILES = {'.git', 'clockInfo.txt', 'dfx_runtime.txt'}
MANIFEST = 'zss/SNAPSHOT_MANIFEST.json'


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b''):
            h.update(chunk)
    return h.hexdigest()


def snapshot_files(root: Path):
    """Select actual content, independently of Git's ignore rules."""
    for directory, names, files in os.walk(root, followlinks=False):
        base = Path(directory)
        kept = []
        for name in sorted(names):
            path = base / name
            relative = path.relative_to(root).as_posix() + '/'
            if name in SKIP_DIRS or name.endswith(SKIP_SUFFIXES):
                continue
            if relative.startswith(SKIP_PREFIXES):
                continue
            if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
                raise ValueError(f'Cannot snapshot directory link: {relative}')
            kept.append(name)
        names[:] = kept
        for name in sorted(files):
            path = base / name
            relative = path.relative_to(root).as_posix()
            if (name in SKIP_FILES or path.suffix in {'.dcp', '.pyc', '.jou', '.str', '.dmp'}
                    or (base == root and (name.startswith('vivado') or name.startswith('hs_err_pid')))):
                continue
            if path.is_symlink():
                raise ValueError(f'Cannot snapshot file link: {relative}')
            yield path, relative


def git_revision(root: Path) -> str | None:
    result = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root,
                            capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def create_snapshot(root: Path, output: Path) -> dict:
    root, output = root.resolve(), output.resolve()
    partial = output.with_suffix(output.suffix + '.partial')
    for path in (output, partial, Path(str(output) + '.sha256'), Path(str(output) + '.json')):
        if path.exists():
            raise FileExistsError(f'Refusing to overwrite: {path}')
    output.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    with zipfile.ZipFile(partial, 'x', allowZip64=True) as archive:
        for path, relative in snapshot_files(root):
            if path.resolve() in (output, partial):
                continue
            before = path.stat()
            info = zipfile.ZipInfo.from_file(path, 'zss/' + relative)
            # Already compressed / very large captures need no expensive recompression.
            info.compress_type = (zipfile.ZIP_STORED if path.suffix in {'.npz', '.zip', '.gz', '.xsa'}
                                  or before.st_size > 32 * CHUNK else zipfile.ZIP_DEFLATED)
            h = hashlib.sha256()
            count = 0
            with path.open('rb') as source, archive.open(info, 'w', force_zip64=True) as target:
                for chunk in iter(lambda: source.read(CHUNK), b''):
                    target.write(chunk)
                    h.update(chunk)
                    count += len(chunk)
            after = path.stat()
            if count != before.st_size or after.st_size != before.st_size or after.st_mtime_ns != before.st_mtime_ns:
                raise RuntimeError(f'File changed during snapshot: {relative}')
            entries.append({'path': relative, 'bytes': count, 'sha256': h.hexdigest()})
            if len(entries) % 1000 == 0:
                print(f'Packed {len(entries)} files', flush=True)
        manifest = {'schema': 1, 'git_head': git_revision(root),
                    'excluded_directory_names': sorted(SKIP_DIRS),
                    'excluded_prefixes': list(SKIP_PREFIXES),
                    'note': 'No Git history, virtualenv, SD image or incremental Vivado DCP. See tools/make_handoff_zip.py for complete exclusions.',
                    'files': entries}
        archive.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'),
                         compress_type=zipfile.ZIP_DEFLATED)
    # rename on Windows refuses an existing destination; precheck also protects other hosts.
    if output.exists():
        raise FileExistsError(output)
    partial.rename(output)
    sha = digest(output)
    receipt = {'schema': 1, 'archive': output.name, 'sha256': sha,
               'bytes': output.stat().st_size, 'file_count': len(entries),
               'uncompressed_bytes': sum(x['bytes'] for x in entries),
               'git_head': manifest['git_head']}
    Path(str(output) + '.sha256').write_text(f'{sha}  {output.name}\n', encoding='utf-8')
    Path(str(output) + '.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return receipt


def verify_extract(archive_path: Path, destination: Path) -> dict:
    """Extract into a new directory and validate every member against the manifest."""
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(f'Extraction requires a new directory: {destination}')
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive member')
        manifest = json.loads(archive.read(MANIFEST))
        entries = manifest['files']
        expected = {MANIFEST} | {'zss/' + entry['path'] for entry in entries}
        if len(entries) != len(expected) - 1 or set(names) != expected:
            raise ValueError('Archive contents differ from manifest')
        for name in names:
            parts = PurePosixPath(name).parts
            if not parts or parts[0] != 'zss' or '..' in parts or '\\' in name or ':' in name:
                raise ValueError(f'Unsafe archive member: {name}')
        destination.mkdir(parents=True)
        for i, entry in enumerate(entries):
            name = 'zss/' + entry['path']
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            h = hashlib.sha256()
            size = 0
            with archive.open(name) as source, target.open('xb') as out:
                for chunk in iter(lambda: source.read(CHUNK), b''):
                    out.write(chunk)
                    h.update(chunk)
                    size += len(chunk)
            if size != entry['bytes'] or h.hexdigest() != entry['sha256']:
                raise ValueError(f'Hash/size mismatch: {name}')
            if (i + 1) % 1000 == 0:
                print(f'Extracted and verified {i + 1} files', flush=True)
        (destination / MANIFEST).write_bytes(archive.read(MANIFEST))
    return {'file_count': len(entries), 'all_hashes_match': True,
            'git_head': manifest['git_head']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, nargs='?', default=Path('dist/zss_handoff.zip'))
    parser.add_argument('--extract-to', type=Path, help='Verify and extract the named archive into a NEW directory')
    args = parser.parse_args()
    if args.extract_to:
        result = verify_extract(args.output, args.extract_to)
    else:
        root = Path(__file__).resolve().parents[1]
        for required in ('vendor/atk', 'src/ps', 'third_party/hdl', 'third_party/no-OS',
                         'board/overlay/sentinel_v2_100m/sentinel_v2_100m.bit'):
            if not (root / required).exists():
                raise FileNotFoundError(f'Missing required snapshot content: {required}')
        result = create_snapshot(root, args.output)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
