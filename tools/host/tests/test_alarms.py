from pathlib import Path
import sys
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sentinel_host.alarms import Alarms


def test_occupancy_range_and_cooldown(tmp_path):
    a=Alarms([dict(name='test',min_hz=90,max_hz=110,ratio=.5,cooldown_s=10)])
    x=np.array([80,100,120]);v=np.array([1,.6,1])
    assert len(a.evaluate(x,v,0)) == 1
    assert not a.evaluate(x,v,9)
    assert len(a.evaluate(x,v,10)) == 1
    path=tmp_path/'bad.yaml';path.write_text('occupancy: [{name: foo}]')
    with pytest.raises(ValueError):
        Alarms.load(path)
