from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'tools/host'), str(ROOT/'src/ps')]
from sentinel_host.model import Model


def test_occupancy_from_detections_and_lo_epoch():
    m = Model(occupancy_seconds=2)
    h = dict(type='spectrum', lo_hz=96050000, frequency_start_hz=94130000, bin_spacing_hz=3750)
    payload = np.arange(1024, dtype='<i2').tobytes()
    m.apply(h, payload, observed=0)
    target = dict(frequency_hz=94130000, bandwidth_hz=3750)
    m.apply(dict(type='detections', targets=[target]), observed=0)
    m.apply(dict(type='detections', targets=[]), observed=1)
    assert m.occupancy_ratio()[0] == .5
    m.apply(dict(type='detections', targets=[]), observed=3)
    assert m.occupancy_ratio()[0] == 0
    m.apply(dict(h, lo_hz=2450000000), payload, observed=4)
    assert len(m.occupancy) == 0


def test_only_known_sent_label_counts_accuracy_and_state_bounded():
    m = Model()
    record = dict(type='amc', track=0, prediction='FM')
    m.apply(record)
    assert not m.confusion
    m.apply(dict(type='demo', sent_label='QPSK'))
    m.apply(record)
    assert not m.confusion
    m.apply(dict(record, transmitted='QPSK'))
    assert m.confusion[('QPSK','FM')] == 1
    for i in range(2100):
        m.apply(dict(type='event', text=str(i)))
    assert len(m.events) == 2000
