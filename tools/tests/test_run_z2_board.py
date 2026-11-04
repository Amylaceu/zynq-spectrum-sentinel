"""Z2 transport gates: immutable implementation and bounded capture retrieval."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_z2_board as runner


@pytest.mark.parametrize('name', ['../escape.npz', '/escape.npz', 'sub/file.npz',
                                 'sub\\file.npz', 'capture.txt'])
def test_capture_paths_cannot_escape(name):
    with pytest.raises(ValueError, match='Unsafe'):
        runner.checked_capture_names({'records': [{'capture_filename': name}]})


def test_duplicate_capture_rejected():
    with pytest.raises(ValueError, match='Duplicate'):
        runner.checked_capture_names({'records': [
            {'capture_filename': 'capture_00000.npz'}]*2})


def test_capture_list_is_explicit_and_includes_sidecars():
    assert runner.checked_capture_names({'records': [
        {'capture_filename': 'capture_00000.npz'}]}) == [
            'result.json', 'result.json.sha256', 'capture_00000.npz',
            'capture_00000.npz.sha256']


@pytest.mark.parametrize('status,image,pre', [
    ('FAIL', 'sentinel_z2', 'hash'), ('PASS', 'sentinel_v1d', 'hash'),
    ('PASS', 'sentinel_z2', 'changed')])
def test_unaccepted_image_rejected_before_payload_or_board(monkeypatch, tmp_path,
                                                         status, image, pre):
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    monkeypatch.setattr(runner, 'verify', lambda attempt: (tmp_path/'frozen', {}))
    monkeypatch.setattr(runner, 'sha', lambda path: 'hash')
    monkeypatch.setattr(runner, 'verified', lambda path: dict(
        status=status, image=image, prebuild_manifest_sha256=pre))
    with pytest.raises(ValueError, match='audited Z2'):
        runner.payload_files(1)
