import base64
import json
import numpy as np
import pytest
from sentinel_host.panorama_live import LivePanorama, ProgressTail

def packet(index=0):
    return dict(type='pano_tile', schema=1, group='A', index=index, total=2,
        lo_hz=75000000+9000000*index, sample_rate_hz=30720000, nfft=4096,
        provisional=True, psd_f32_base64=base64.b64encode(np.full(4096, 1e-10, dtype='<f4').tobytes()).decode())

def test_live_tiles_are_masked_provisional_and_ordered():
    live = LivePanorama()
    x, y = live.apply(packet())
    assert x.min() >= 70 or np.isnan(x.min())
    assert not np.any((x > 74.85) & (x < 75.15))
    assert np.isnan(y[-1])
    live.apply(packet(1))
    with pytest.raises(ValueError):
        live.apply(packet(1))

@pytest.mark.parametrize('key,value', [('lo_hz', 2.45e9), ('sample_rate_hz', 3840000),
    ('psd_f32_base64', 'garbage'), ('provisional', False), ('total', 9999)])
def test_invalid_tile_rejected(key, value):
    value_packet = packet()
    value_packet[key] = value
    with pytest.raises(ValueError):
        LivePanorama().apply(value_packet)

def test_tail_preserves_partial_line_and_no_duplicate(tmp_path):
    path = tmp_path/'progress.jsonl'
    tail = ProgressTail(path)
    assert tail.poll() == []
    raw = json.dumps(packet()).encode()
    path.write_bytes(raw[:100])
    assert tail.poll() == [] and tail.offset == 0
    with path.open('ab') as out:
        out.write(raw[100:]+b'\n')
    assert len(tail.poll()) == 1
    assert tail.poll() == []
