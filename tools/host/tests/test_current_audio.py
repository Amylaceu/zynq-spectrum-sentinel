"""Current-session playback refuses stale, altered or unverified recordings."""
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sentinel_host.current_audio import verified_current_audio


def recording(path, **overrides):
    wav = path/'current_recording.wav'
    wav.write_bytes(b'test payload; no actual audio playback in tests')
    record = dict(session_id='current-request', status='READY_FOR_LISTENING',
        source='CURRENT_RF_IQ_SOFTWARE_FM_DEMOD', synthetic=False,
        inserted_silence_samples=0, stitched_snapshot_gaps=False,
        wav=wav.name, wav_sha256=hashlib.sha256(wav.read_bytes()).hexdigest())
    record.update(overrides)
    metadata = path/'audio.json'
    metadata.write_text(json.dumps(record))
    Path(str(metadata)+'.sha256').write_text(hashlib.sha256(metadata.read_bytes()).hexdigest())
    return wav


def test_accepts_only_expected_session(tmp_path):
    wav = recording(tmp_path)
    assert verified_current_audio(tmp_path, 'current-request')[0] == wav
    with pytest.raises(ValueError):
        verified_current_audio(tmp_path, 'previous-request')


@pytest.mark.parametrize('field,value', [('synthetic', True), ('stitched_snapshot_gaps', True),
    ('inserted_silence_samples', 4800), ('status', 'QUALITY_UNCONFIRMED'), ('wav', '../old.wav')])
def test_rejects_noncurrent_or_incomplete_sources(tmp_path, field, value):
    recording(tmp_path, **{field: value})
    with pytest.raises(ValueError):
        verified_current_audio(tmp_path, 'current-request')


def test_refuses_tampered_audio_and_metadata(tmp_path):
    wav = recording(tmp_path)
    wav.write_bytes(b'altered')
    with pytest.raises(ValueError, match='WAV digest'):
        verified_current_audio(tmp_path, 'current-request')
    recording(tmp_path)
    (tmp_path/'audio.json').write_text('{}')
    with pytest.raises(ValueError, match='metadata digest'):
        verified_current_audio(tmp_path, 'current-request')
