"""Backup roundtrip and tamper checks; no board or original SD access."""
import json
from pathlib import Path
import sys
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from make_handoff_zip import create_snapshot, verify_extract
from make_incremental_snapshot import create_incremental, verify_incremental, INCREMENTAL_MANIFEST


def test_incremental_restores_same_size_edit_and_ignored_capture(tmp_path):
    root = tmp_path/'repo'
    root.mkdir()
    (root/'source.py').write_bytes(b'old')
    (root/'unchanged').write_bytes(b'keep')
    base = root/'dist/base.zip'
    create_snapshot(root, base)
    (root/'source.py').write_bytes(b'new')
    (root/'board/measurements').mkdir(parents=True)
    (root/'board/measurements/raw.npz').write_bytes(b'raw-data')
    output = root/'dist/increment.zip'
    receipt = create_incremental(root, base, output)
    assert receipt['all_payload_hashes_verified'] and receipt['file_count'] == 2
    manifest = verify_incremental(output)
    assert {x['path'] for x in manifest['files']} == {'source.py', 'board/measurements/raw.npz'}
    restored = tmp_path/'restored'
    verify_extract(base, restored)
    with zipfile.ZipFile(output) as archive:
        archive.extractall(restored)
    assert (restored/'zss/source.py').read_bytes() == b'new'
    assert (restored/'zss/unchanged').read_bytes() == b'keep'
    assert (restored/'zss/board/measurements/raw.npz').read_bytes() == b'raw-data'
    with pytest.raises(FileExistsError):
        create_incremental(root, base, output)
    Path(str(base)+'.sha256').write_text('0'*64)
    with pytest.raises(ValueError, match='hash mismatch'):
        create_incremental(root, base, root/'dist/other.zip')


def test_incremental_rejects_corrupt_payload(tmp_path):
    path = tmp_path/'bad.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('zss/file', b'bad')
        archive.writestr(INCREMENTAL_MANIFEST, json.dumps(dict(files=[
            dict(path='file', bytes=3, sha256='0'*64)])))
    with pytest.raises(ValueError, match='integrity mismatch'):
        verify_incremental(path)
