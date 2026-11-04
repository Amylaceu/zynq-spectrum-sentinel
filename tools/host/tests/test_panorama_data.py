import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sentinel_host.panorama_data import load_panorama, local_file


def seal(path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    Path(str(path)+'.sha256').write_text(digest+'  '+path.name+'\n')
    return digest


def artifact(tmp_path):
    data = tmp_path/'panorama.npz'
    np.savez(data, frequency_hz=np.arange(20)*10000.+70000000,
             psd_fs2_per_hz=np.full(20, 1e-10), count=np.ones(20, dtype=np.uint16))
    record = dict(status='PASS_SNAPSHOT_SCAN', group='A', source='RX1A_ANTENNA',
                  scope='FINITE_DISCONTINUOUS_RAW_DMA_SNAPSHOTS', rf_transmission_requested=False,
                  baseline_restore=dict(rate_hz=3840000), stopped=dict(gpio=0, source=0, audio=0),
                  buffers_quarantined=False, tiles=[dict(file=data.name, sha256=seal(data))], panorama=data.name,
                  panorama_sha256=seal(data))
    path = tmp_path/'result.json'
    path.write_text(json.dumps(record))
    seal(path)
    return path, record


def test_validated_snapshot_display_and_tamper_rejection(tmp_path):
    path, record = artifact(tmp_path)
    _, frequency, db, count = load_panorama(path)
    assert len(frequency) == 20 and np.all(db == -100)
    assert np.all(count == 1)
    with (tmp_path/'panorama.npz').open('ab') as f:
        f.write(b'tampered')
    with pytest.raises(ValueError):
        load_panorama(path)


@pytest.mark.parametrize('key,value', [('source', 'SYNTHETIC'), ('rf_transmission_requested', True),
                                     ('buffers_quarantined', True), ('baseline_restore', {})])
def test_reject_unaccepted_records(tmp_path, key, value):
    path, record = artifact(tmp_path)
    record[key] = value
    path.write_text(json.dumps(record))
    seal(path)
    with pytest.raises(ValueError):
        load_panorama(path)


@pytest.mark.parametrize('name', ['../outside.npz', 'a/b.npz', 'a\\b.npz'])
def test_reject_path_escape(tmp_path, name):
    with pytest.raises(ValueError):
        local_file(tmp_path, name)
