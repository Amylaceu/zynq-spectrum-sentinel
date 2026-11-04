"""Windows-sized capture collections must stay explicit and bounded."""
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from x5_transfer import retrieval_commands, retrieve_files


def test_large_capture_set_keeps_order_without_command_overflow():
    names = ['capture_%05d.npz%s' % (index, suffix)
             for index in range(1200) for suffix in ('', '.sha256')]
    directory = '/home/xilinx/sentinel/setup/x5_station_r1_runtime/measurements/x5_station_r1'
    commands = retrieval_commands('xilinx@192.0.2.1', directory, names, 'C:/measurements', ['-B'])
    actual = []
    assert len(commands) > 1
    for command in commands:
        assert command[:2] == ['scp', '-B']
        assert len(subprocess.list2cmdline(command)) < 24000
        assert len(command[2:-1]) <= 64
        actual.extend(value.rsplit('/', 1)[1] for value in command[2:-1])
    assert actual == names


@pytest.mark.parametrize('names', [[], ['x', 'x'], ['../x'], ['/x'], ['.'], ['..'], ['a\\x']])
def test_unsafe_or_duplicate_files_rejected(names):
    with pytest.raises(ValueError):
        retrieval_commands('user@host', '/measurements', names, 'out')


def test_single_overlong_path_rejected():
    with pytest.raises(ValueError, match='exceeds'):
        retrieval_commands('user@host', '/measurements', ['x'*300], 'out', limit=100)


def test_failed_transfer_stops_later_batches(monkeypatch):
    calls = []
    def fail(command, **kwargs):
        calls.append((command, kwargs))
        raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(subprocess, 'run', fail)
    with pytest.raises(subprocess.CalledProcessError):
        retrieve_files('user@host', '/measurements', ['x%03d' % i for i in range(200)], 'out')
    assert len(calls) == 1
    assert calls[0][1] == dict(check=True, timeout=180)
