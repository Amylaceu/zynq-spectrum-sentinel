"""Protocol boundaries and real command/reply UI ownership, without PYNQ."""
import time
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'tools/host'), str(ROOT/'src/ps')]
from sentinel.app.hostlink_protocol import validate_command, ProtocolError


def request(**changes):
    args = dict(id='F1', action='start', mode='CA', alpha=1974); args.update(changes)
    return dict(type='command', seq=1, t_mono=1., len=0, command='feature', args=args)


@pytest.mark.parametrize('identity', ['F%d' % i for i in range(1, 11)])
def test_receive_only_presets(identity):
    assert validate_command(request(id=identity), 'resident')[0] == 'feature'


@pytest.mark.parametrize('changes', [dict(id='tx'), dict(action='write'), dict(alpha=True),
    dict(alpha=8193), dict(alpha=0), dict(mode='GO; tx'), dict(address=0)])
def test_rejects_unbounded_request(changes):
    with pytest.raises(ProtocolError): validate_command(request(**changes), 'resident')


def test_not_available_to_monitor():
    with pytest.raises(ProtocolError): validate_command(request(), 'monitor')


def test_stop_requires_matching_readback_reply():
    from product import app_instance
    from sentinel_host.features_v6 import Window
    app = app_instance(); w = Window(ROOT)
    class Worker:
        def command(self, *_args, **_kwargs): return 18
        def requestInterruption(self): pass
        def wait(self, *_): pass
    w.worker = Worker(); w.active = 'F2'; w.stop_feature()
    assert '已恢复默认' not in w.state.text()
    w.packet(dict(type='reply', request_seq=17, ok=True, feature=dict(status='STOPPED', restored=True)), b'', time.monotonic())
    assert w.active == 'F2'
    w.packet(dict(type='reply', request_seq=18, ok=True, feature=dict(status='STOPPED', restored=True)), b'', time.monotonic())
    assert w.active is None and w.frozen
    assert '已恢复默认' in w.state.text()
    w.worker = None; w.close(); app.processEvents()


def test_data_reply_cannot_be_mistaken_for_restore():
    from product import app_instance
    from sentinel_host.features_v6 import Window
    app = app_instance(); w = Window(ROOT)
    w.pending = dict(seq=3, id='F4', action='stop', started=time.monotonic())
    w.packet(dict(type='reply', request_seq=3, ok=True, feature=dict(status='STOPPED', restored=False)), b'', time.monotonic())
    assert '已恢复默认' not in w.state.text()
    w.close(); app.processEvents()


def test_audio_quality_mute_is_visible_and_external_stop_clears_state():
    from product import app_instance
    from sentinel_host.features_v6 import Window
    app = app_instance(); w = Window(ROOT); w.active = w.selected = 'F8'
    w.packet(dict(type='telemetry', scene='F8', audio=dict(output_unmuted=False,
        pcm_samples=48000, underflows=0), pilot=dict(pilot_prominence_db=18)), b'', time.monotonic())
    assert '自动静音' in w.state.text()
    w.packet(dict(type='telemetry', scene='idle'), b'', time.monotonic())
    assert w.active is None and w.frozen
    w.close(); app.processEvents()
