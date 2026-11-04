import json
import numpy as np
import pytest
from src.ps.sentinel.artifacts import atomic_write, atomic_json


def test_failed_writer_preserves_previous_measurement(tmp_path):
    path = tmp_path/'measurement.json'
    atomic_json(path, {'status': 'previous'})

    def interrupted(stream):
        stream.write(b'incomplete')
        raise OSError('simulated capture write failure')

    with pytest.raises(OSError):
        atomic_write(path, interrupted)
    assert json.loads(path.read_text()) == {'status': 'previous'}
    assert list(tmp_path.iterdir()) == [path]


def test_saved_capture_can_be_independently_reopened(tmp_path):
    values = np.arange(128, dtype=np.int16).reshape(-1, 4)
    path = tmp_path/'capture.npz'
    atomic_write(path, lambda stream: np.savez_compressed(stream, received=values))
    with np.load(path) as archive:
        assert np.array_equal(archive['received'], values)
