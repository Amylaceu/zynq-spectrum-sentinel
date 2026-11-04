import json
import wave

import pytest

from sentinel_host.pcm_recording import PCMRecording,sha


def header(index,count=2):
    return dict(source='ps_parallel_demod',sample_rate_hz=48000,channels=1,
                format='s16le',first_sample_index=index,samples=count)


def test_real_pcm_and_explicit_gap_sidecar(tmp_path):
    path=tmp_path/'real.wav'
    writer=PCMRecording(path)
    writer.append(header(100),b'\x01\x00\x02\x00')
    writer.append(header(105),b'\x03\x00\x04\x00')
    writer.close();writer.close()
    with wave.open(str(path),'rb') as stream:
        assert stream.getnframes()==7
        assert stream.readframes(7)==b'\x01\x00\x02\x00'+bytes(6)+b'\x03\x00\x04\x00'
    data=json.loads(path.with_suffix('.wav.json').read_text())
    assert data['gaps'][0]['samples']==3
    assert not data['adc_continuity_certified']
    assert data['wav_sha256']==sha(path)
    assert path.with_suffix('.wav.json.sha256').read_text().split()[0]==sha(path.with_suffix('.wav.json'))
    with pytest.raises(FileExistsError):PCMRecording(path)


@pytest.mark.parametrize('change',[
    {'source':'pl_playback_mirror'}, {'synthetic':True}, {'first_sample_index':99},
    {'samples':4}, {'fifo_overflow':True}, {'sample_rate_hz':44100}])
def test_reject_invalid_source_gap_or_length_and_close_incomplete(tmp_path,change):
    path=tmp_path/'invalid.wav';writer=PCMRecording(path)
    writer.append(header(100),bytes(4))
    h=header(102);h.update(change)
    with pytest.raises(ValueError):writer.append(h,bytes(4))
    assert writer.closed
    assert json.loads(path.with_suffix('.wav.json').read_text())['status']=='INCOMPLETE'
