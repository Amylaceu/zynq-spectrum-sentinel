"""Meaningful lifecycle, safe readiness failure and strict command boundaries."""
from contextlib import nullcontext
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'src/ps'))
from sentinel.app.resident import ResidentController, SceneUnavailable, validate_request, ReceiveBackend
from sentinel.app.resident_control import LocalControl
from sentinel.app.hostlink_protocol import validate_command, ProtocolError


class Clock:
    def __init__(self):
        self.now = 0.
    def __call__(self):
        return self.now
    def sleep(self, seconds):
        self.now += seconds


class Backend:
    def __init__(self):
        self.events = []
        self.is_ready = True
        self.scene = 'idle'
        self.fault = False
    def paused(self):
        return nullcontext()
    def mute(self):
        self.events.append('mute')
    def readback(self):
        self.events.append('readback')
        return dict(tx_attenuation_db=[89.75, 89.75], source_ctrl=1, gpio_data=1)
    def enter_scene(self, scene):
        self.events.append('enter:'+scene)
        self.scene = scene
    def safety(self):
        if self.fault:
            raise RuntimeError('DMA fault')
    def ready(self, scene):
        return dict(ready=self.is_ready)
    def close(self):
        self.events.append('close_and_reset')


def controller():
    clock, backend = Clock(), Backend()
    return ResidentController(backend, clock, clock.sleep), backend


def test_fifty_switches_preserve_owner_and_mute_before_every_scene():
    owner, backend = controller()
    for scene in ['check', 'fm', 'listen', 'perf', 'idle']*10:
        assert owner.switch(scene)['status'] == 'READY'
    assert backend.events.count('close_and_reset') == 0
    assert backend.events.count('mute') == 50
    for i, event in enumerate(backend.events):
        if event.startswith('enter:'):
            assert backend.events[i-2:i] == ['mute', 'readback']
    owner.close()
    owner.close()
    assert backend.events.count('close_and_reset') == 1


def test_weak_signal_never_accepted_and_falls_back_muted_without_rf_reset():
    owner, backend = controller()
    backend.is_ready = False
    record = owner.switch('listen')
    assert record['status'] == 'NOT_READY'
    assert record['elapsed_s'] >= 3
    assert owner.scene == backend.scene == 'idle'
    assert backend.events[-3:] == ['mute', 'enter:idle', 'readback']
    assert 'close_and_reset' not in backend.events


def test_hardware_fault_cleans_once_and_does_not_retry_failed_dma():
    owner, backend = controller()
    backend.fault = True
    with pytest.raises(RuntimeError, match='DMA fault'):
        owner.switch('fm')
    assert owner.closed and backend.events.count('close_and_reset') == 1
    with pytest.raises(RuntimeError, match='stopping'):
        owner.switch('listen')


@pytest.mark.parametrize('scene', ['ota', 'noise', 'pano', 'wifi'])
def test_unimplemented_scenes_rejected_before_touching_hardware(scene):
    owner, backend = controller()
    with pytest.raises(SceneUnavailable):
        owner.switch(scene)
    assert backend.events == []


@pytest.mark.parametrize('message', [dict(command='tx'), dict(command='scene', id='listen', volume=0),
    dict(command='scene', id='__import__'), dict(command='stop', id='fm'), [], None])
def test_control_has_no_arbitrary_tx_frequency_or_extra_parameters(message):
    with pytest.raises(ValueError):
        validate_request(message)


def test_network_scene_is_only_allowed_in_resident_mode():
    header = dict(type='command', seq=1, t_mono=0, len=0, command='scene', args=dict(id='fm'))
    assert validate_command(header, 'resident') == ('scene', dict(id='fm'))
    for mode in ('monitor', 'listen', 'demo'):
        with pytest.raises(ProtocolError):
            validate_command(header, mode)
    header['args']['tx_attenuation'] = 0
    with pytest.raises(ProtocolError):
        validate_command(header, 'resident')


def test_stop_prevents_further_scene_switches():
    owner, _ = controller()
    assert owner.dispatch(dict(command='stop'))['status'] == 'STOP_REQUESTED'
    with pytest.raises(RuntimeError):
        owner.switch('fm')


def test_listen_pauses_source_around_audio_fifo_reset_without_resetting_rf(tmp_path):
    from types import SimpleNamespace
    events = []
    backend = ReceiveBackend(tmp_path, tmp_path)
    backend.config = dict(station_hz=95800000, lo_hz=96050000)
    backend.codec = object()
    backend.tracker = SimpleNamespace(tracks={})
    backend._present = lambda **kwargs: None
    backend.hw = SimpleNamespace(
        lcd=SimpleNamespace(registers=SimpleNamespace(read=lambda _: 10)),
        source=SimpleNamespace(stop=lambda: events.append('source_stop'),
                               start=lambda: events.append('source_start')),
        audio=SimpleNamespace(snapshot=lambda: dict(pcm_samples=0),
            configure=lambda *args: events.append('audio_config'),
            start=lambda: events.append('audio_start')))
    backend.enter_scene('listen')
    assert events == ['source_stop', 'audio_config', 'audio_start', 'source_start']
    events.clear()
    backend.enter_scene('fm')
    assert events == []


def test_mute_preserves_codec_initialization_and_rf_ownership(tmp_path):
    from types import SimpleNamespace
    events = []
    backend = ReceiveBackend(tmp_path, tmp_path)
    backend.codec = SimpleNamespace(initialized=True, MUTE=0x26,
        checked=lambda *args: events.append(('mute', args)))
    backend.hw = SimpleNamespace(audio=SimpleNamespace(
        disable=lambda **kwargs: events.append(('disable', kwargs))))
    backend.audible = True
    backend.mute()
    assert backend.codec.initialized and not backend.audible
    assert events == [('mute', (0x19, 0x26)), ('disable', dict(release_pins=False))]


@pytest.mark.skipif(sys.platform == 'win32', reason='Board uses AF_UNIX; not Windows filesystem sockets')
def test_existing_control_socket_is_not_unlinked(tmp_path):
    path = tmp_path/'socket'
    path.write_text('owned')
    with pytest.raises(RuntimeError):
        with LocalControl(lambda x: x, path):
            pass
    assert path.read_text() == 'owned'
