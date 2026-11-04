from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'tools/host'), str(ROOT/'src/ps')]
from sentinel_host.session import Recorder, Replay


def test_lossless_record_replay_and_no_pickle(tmp_path):
    stamp = [10.]
    recorder = Recorder(tmp_path/'test.zsr', clock=lambda: stamp[0], source='synthetic-test')
    expected = []
    for index, payload in enumerate((b'', b'\n\x00\xff'*100, b'\0'*4096)):
        header = dict(type='spectrum' if payload else 'event', seq=index, t_mono=index, len=len(payload))
        recorder.append(header, payload)
        expected.append((stamp[0]-10, header, payload))
        stamp[0] += .1
    recorder.close()
    assert list(Replay(recorder.path)) == expected
    (recorder.path/'session.jsonl').write_text('modified')
    with pytest.raises(ValueError, match='checksum'):
        Replay(recorder.path)


def test_incomplete_or_overwrite_refused(tmp_path):
    path = tmp_path/'test.zsr'
    r = Recorder(path)
    with pytest.raises(FileNotFoundError):
        Replay(path)
    with pytest.raises(FileExistsError):
        Recorder(path)
    r.close()
