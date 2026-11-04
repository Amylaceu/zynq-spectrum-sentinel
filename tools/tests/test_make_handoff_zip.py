"""Snapshot portability, exclusion and integrity checks without board access."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from make_handoff_zip import create_snapshot, verify_extract


def test_roundtrip_includes_ignored_assets_and_excludes_build_caches(tmp_path):
    root = tmp_path / 'repo'
    included = ['vendor/atk/schematic.pdf', 'board/overlay/sentinel_v2_100m/image.bit',
                'board/measurements/raw.npz', 'report/results/evidence.zip',
                'build/reports/final/timing.rpt', 'third_party/hdl/source.v',
                'src/ps/models/weights/model.pt', 'data/synthetic/train.npz']
    excluded = ['.git/config', 'third_party/hdl/.git', '.venv/bin/python',
                'logs/run.log', 'build/work/output.bit', 'build/sd_boot_backup/full.img',
                'build/reports/checkpoint.dcp', 'project.runs/output.bit',
                '.pytest_cache/cache', 'dist/old.zip']
    for name in included + excluded:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
    archive = root / 'dist/snapshot.zip'
    receipt = create_snapshot(root, archive)
    assert receipt['file_count'] == len(included)
    assert receipt['sha256'] == hashlib.sha256(archive.read_bytes()).hexdigest()
    destination = tmp_path / 'restored'
    result = verify_extract(archive, destination)
    assert result['all_hashes_match']
    for name in included:
        assert (destination / 'zss' / name).read_bytes() == (root / name).read_bytes()
    for name in excluded:
        assert not (destination / 'zss' / name).exists()
    with pytest.raises(FileExistsError):
        create_snapshot(root, archive)
    with pytest.raises(FileExistsError):
        verify_extract(archive, destination)


@pytest.mark.parametrize('name,sha', [('payload.txt', '0' * 64), ('../escape.txt', hashlib.sha256(b'x').hexdigest())])
def test_rejects_tampered_or_traversing_archive(tmp_path, name, sha):
    archive = tmp_path / 'bad.zip'
    manifest = {'files': [{'path': name, 'bytes': 1, 'sha256': sha}]}
    with zipfile.ZipFile(archive, 'w') as out:
        out.writestr('zss/SNAPSHOT_MANIFEST.json', json.dumps(manifest))
        out.writestr('zss/' + name, b'x')
    with pytest.raises(ValueError):
        verify_extract(archive, tmp_path / 'out')
    assert not (tmp_path / 'escape.txt').exists()
