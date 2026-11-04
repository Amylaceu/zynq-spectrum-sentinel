from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'tools/host'),str(ROOT/'src/ps')]
from sentinel_host.model import Model
from sentinel_host.session import Recorder,Replay


def test_replay_speed_does_not_change_occupancy_or_events(tmp_path):
    stamp=[0.]
    rec=Recorder(tmp_path/'test.zsr',clock=lambda:stamp[0],source='synthetic-test')
    headers=[dict(type='spectrum',lo_hz=96e6,frequency_start_hz=94.08e6,bin_spacing_hz=3750),
        dict(type='detections',targets=[dict(frequency_hz=95.8e6,bandwidth_hz=1e5)]),
        dict(type='detections',targets=[]),dict(type='event',text='known event'),
        dict(type='amc',track=1,prediction='FM',transmitted='FM')]
    for i,h in enumerate(headers):
        payload=np.ones(1024,dtype='<i2').tobytes() if i==0 else b''
        h.update(seq=i,t_mono=100+i,len=len(payload))
        rec.append(h,payload);stamp[0]+=.5
    rec.close()
    states=[]
    for speed in (1,2):
        m=Model()
        for elapsed,header,payload in Replay(rec.path):
            m.apply(header,payload,observed=elapsed/speed)
        states.append(m)
    assert np.array_equal(states[0].occupancy_ratio(),states[1].occupancy_ratio())
    assert states[0].targets==states[1].targets
    assert states[0].events==states[1].events
    assert states[0].confusion==states[1].confusion
