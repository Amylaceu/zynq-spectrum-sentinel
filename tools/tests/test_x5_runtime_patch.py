"""PS fixes cannot relabel a modified RTL build as accepted hardware."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import x5_runtime_patch as patch
from x2_transport import sha, write_evidence


def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(patch, 'ROOT', tmp_path)
    for name in ('src/ps/sentinel/v1d.py', 'src/rtl/core.v',
                 'board/overlay/sentinel_v1d/sentinel_v1d.bit'):
        path = tmp_path/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'original fixture')
    base = tmp_path/'docs/x5_v1d_prebuild_r2.json'
    base.parent.mkdir()
    write_evidence(base, dict(sources_sha256={name: sha(tmp_path/name) for name in (
        'src/ps/sentinel/v1d.py', 'src/rtl/core.v')}))
    accepted = tmp_path/'board/overlay/sentinel_v1d/acceptance.json'
    write_evidence(accepted, dict(status='PASS', image='sentinel_v1d',
        prebuild_manifest_sha256=sha(base),
        artifacts_sha256={'sentinel_v1d.bit': sha(accepted.parent/'sentinel_v1d.bit')}))
    return base


def test_ps_patch_preserves_original_manifest_bytes(tmp_path, monkeypatch):
    base = fixture(tmp_path, monkeypatch)
    original = base.read_bytes()
    (tmp_path/'src/ps/sentinel/v1d.py').write_bytes(b'PYNQ metadata compatibility fix')
    _, _, changes = patch.hardware_base(2)
    assert set(changes) == {'src/ps/sentinel/v1d.py'}
    assert base.read_bytes() == original


@pytest.mark.parametrize('name', ['src/rtl/core.v',
    'board/overlay/sentinel_v1d/sentinel_v1d.bit'])
def test_hardware_changes_are_never_allowed_as_ps_patch(tmp_path, monkeypatch, name):
    fixture(tmp_path, monkeypatch)
    (tmp_path/name).write_bytes(b'changed')
    with pytest.raises(ValueError):
        patch.hardware_base(2)


def test_relabelled_original_prebuild_fails_acceptance_link(tmp_path, monkeypatch):
    base = fixture(tmp_path, monkeypatch)
    base.write_bytes(base.read_bytes()+b'\n')
    Path(str(base)+'.sha256').write_text(sha(base)+'  '+base.name+'\n')
    with pytest.raises(ValueError, match='original frozen build'):
        patch.hardware_base(2)
