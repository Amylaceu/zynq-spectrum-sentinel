import hashlib
import json
from types import SimpleNamespace

import pytest

from src.ps.sentinel.app.monitor_x1 import checked_bundle, same_frame_entry
from src.ps.sentinel.app.runtime_v1 import Session
from src.ps.sentinel.drivers.cfar import Target
from src.ps.sentinel.drivers.cfar_x1 import CfarSnapshot
from src.ps.sentinel.drivers.regs import cfar_x1 as C, spec_ctrl as F
from src.ps.sentinel.v1b import V1b


def test_bundle_refuses_unaccepted_or_old_cfar_and_corrupt_artifact(tmp_path):
    hashes = {}
    for suffix in ('bit','hwh','xsa'):
        path = tmp_path/('sentinel_v1b.'+suffix)
        path.write_bytes(suffix.encode())
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    path = tmp_path/'acceptance.json'
    acceptance = {'status':'PASS','cfar_version':C.VERSION_VALUE,'artifacts_sha256':hashes}
    path.write_text(json.dumps(acceptance))
    assert checked_bundle(tmp_path/'sentinel_v1b.bit') == acceptance
    for update in ({'status':'FAIL'}, {'cfar_version':0x43460001}):
        path.write_text(json.dumps(dict(acceptance,**update)))
        with pytest.raises(RuntimeError):
            checked_bundle(tmp_path/'sentinel_v1b.bit')
    path.write_text(json.dumps(acceptance))
    (tmp_path/'sentinel_v1b.hwh').write_bytes(b'wrong')
    with pytest.raises(RuntimeError,match='hash mismatch'):
        checked_bundle(tmp_path/'sentinel_v1b.bit')


def test_report_uses_one_snapshot_for_list_status_and_counters():
    target = Target(12,16,14,1,100,250)
    snap = CfarSnapshot(43,16,100,40,7,33,(target,))
    entry = same_frame_entry(snap)
    assert entry['cfar_sequence'] == 43 and entry['list_overflow']
    assert entry['raw_count']-entry['filtered_count'] == entry['candidate_count']
    assert entry['targets'][0]['flags'] == 1


def test_v1b_waits_for_initial_clear_and_configures_before_source_enable():
    events = []
    states = iter((2,0))
    hw = object.__new__(V1b)
    hw.spec = SimpleNamespace(write=lambda offset,value: events.append(('spec',offset,value)))
    hw.cfar = SimpleNamespace(mmio=SimpleNamespace(read=lambda offset: next(states)),
                              configure=lambda **kw: events.append(('cfar',kw)))
    hw.enable_processing(average_shift=4,min_width_bins=3)
    assert events[0] == ('spec',F.AVG_SHIFT,4)
    assert events[-2] == ('cfar',{'min_width_bins':3})
    assert events[-1] == ('spec',F.CTRL,1)


def test_session_can_select_explicit_x1_binding_without_changing_default():
    from src.ps.sentinel.v1 import V1
    assert Session('unused').hw_factory is V1
    assert Session('unused',hw_factory=V1b).hw_factory is V1b
