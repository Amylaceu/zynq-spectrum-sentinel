"""Install a hashed F1 package while holding both execution locks; no hardware I/O."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import uuid


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--replace', action='store_true')
    parser.add_argument('--candidate', choices=('i1_r1', 'i1_r2', 'i1_r3', 'audio_volume_r1',
                                               'i2_r1', 'i2_r2', 'i2_r3', 'j6_r1', 'j6_r2', 'j6_r3', 'j6_dma_r1', 'j6_audio_r1', 'j6_audio_r2', 'j6_audio_r3', 'j7_r1', 'j7_r2', 'j7_r3', 'j7_final', 'j7_rec3_r1', 'j8_r1', 'j8_r2', 'j8_r3', 'j8_final'),
                        help='Isolated software candidate; keep installed v2 untouched')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Installer requires root')
    if digest(args.archive) != args.sha256:
        raise ValueError('Archive checksum mismatch')
    base = Path('/home/xilinx/sentinel')
    destination = base/'release'/(args.candidate or 'v2')
    # The library was previously accepted on this board. Copy, never recompile.
    library = base/'ps/libad9361_pynq/libad9361_pynq.so'
    with open('/run/lock/zss_release_v2.lock', 'a') as outer, open('/run/lock/zss_ad9361.lock', 'a') as rf:
        for lock in (outer, rf):
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if destination.exists() and not args.replace:
            raise FileExistsError('Existing release preserved; use --replace after stopping it')
        if destination.is_symlink():
            raise ValueError('Unexpected release symlink')
        stage = base/'release'/('staging_'+uuid.uuid4().hex)
        stage.mkdir(parents=True)
        with tarfile.open(args.archive) as tar:
            members = tar.getmembers()
            names = [m.name for m in members]
            if len(names) != len(set(names)):
                raise ValueError('Duplicate package member')
            for m in members:
                p = PurePosixPath(m.name)
                if not m.isfile() or p.is_absolute() or '..' in p.parts or '\\' in m.name or ':' in m.name:
                    raise ValueError('Unsafe package member')
                target = stage.joinpath(*p.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(m) as source, target.open('xb') as out:
                    shutil.copyfileobj(source, out)
                os.chmod(str(target), 0o755 if target.suffix == '.sh' else 0o644)
        manifest_path = stage/'manifest.json'
        if digest(manifest_path) != (stage/'manifest.json.sha256').read_text().split()[0]:
            raise ValueError('Manifest mismatch')
        manifest = json.loads(manifest_path.read_text())
        if set(names) != set(manifest['files']) | {'manifest.json', 'manifest.json.sha256'}:
            raise ValueError('Package member list differs')
        for name, expected in manifest['files'].items():
            if digest(stage/name) != expected:
                raise ValueError('Installed member mismatch: '+name)
        expected_library = 'b329018314e6ecc9c0b11440b0d5449d9670fda7b5d37deabdc55c4731616e83'
        if digest(library) != expected_library:
            raise ValueError('Board library differs from accepted version')
        library_out = stage/'ps/libad9361_pynq/libad9361_pynq.so'
        library_out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(library, library_out)
        if digest(library_out) != expected_library:
            raise ValueError('Copied library hash mismatch')
        for directory in ('measurements', 'logs'):
            (stage/directory).mkdir()
        previous = None
        if destination.exists():
            previous = destination.with_name('v2_previous_'+uuid.uuid4().hex)
            destination.rename(previous)
        try:
            stage.rename(destination)
        except BaseException:
            if previous is not None:
                previous.rename(destination)
            raise
        print(json.dumps(dict(status='INSTALLED_HASH_VERIFIED', root=str(destination),
                              archive_sha256=args.sha256, files=len(manifest['files']),
                              library_sha256=expected_library, previous=str(previous) if previous else None,
                              hardware_started=False)), flush=True)


if __name__ == '__main__':
    main()
