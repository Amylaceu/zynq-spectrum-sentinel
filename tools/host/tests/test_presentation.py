"""Real command correlation, honest feature gates and projector interactions."""
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT/'tools/host'), str(ROOT/'src/ps')]
import pytest
from PySide6 import QtCore, QtWidgets
from PySide6.QtTest import QTest
from sentinel_host.shell import Window
from sentinel_host.presentation import load_scenes
from sentinel_host.gui import Receiver
from sentinel_host.session import Recorder
from sentinel_host.theme import configure


@pytest.fixture
def window():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    configure(app)
    value = Window()
    value.timer.stop()
    value.show()
    app.processEvents()
    sent = []
    def command(name, **args):
        sent.append((len(sent)+1, name, args))
        return len(sent)
    value.worker = SimpleNamespace(session=None, command=command, address='192.0.2.1', token=None)
    value.model.hello = dict(mode='resident')
    value.last_packet_time = time.monotonic()
    value.sent = sent
    value.presentation.toggle()
    app.processEvents()
    try:
        yield value
    finally:
        value.worker = None
        value.close()
        app.processEvents()


def ready(window, scene='check', seq=None):
    pending = window.presentation.pending
    header = dict(type='reply', ok=True, request_seq=seq if seq is not None else pending['seq'],
        scene=dict(status='READY', scene=scene, readiness=dict(ready=True, checks=dict(passed=True))))
    window.presentation.packet(header, time.monotonic())


def test_projector_keeps_frozen_canvas_and_grows_to_1100(window):
    app = QtWidgets.QApplication.instance()
    window.resize(1920, 1080)
    app.processEvents()
    assert window.twin_canvas.viewport().width() >= 1100
    assert all(b.minimumHeight() >= 72 for b in window.presentation.buttons)
    assert not window.presentation_button.isVisible()
    assert window.presentation.dialog.isVisible()
    assert window.mode_badge.isVisible()
    assert window.tx_badge.isVisible()


def test_unavailable_scenes_and_precheck_gate(window):
    presenter = window.presentation
    assert not presenter.buttons[2].isEnabled()
    ready(window)
    assert presenter.checked
    assert presenter.buttons[2].isEnabled()
    for index in (1, 4, 5):
        assert not presenter.buttons[index].isEnabled()
        count = len(window.sent)
        presenter.request(index)
        assert len(window.sent) == count


def test_only_matching_reply_can_unlock_ready(window):
    presenter = window.presentation
    ready(window, seq=999)
    assert presenter.pending is not None and not presenter.checked
    presenter.packet(dict(type='reply', request_seq=1, ok=True,
        scene=dict(status='NOT_READY', scene='check', readiness=dict(ready=False))), time.monotonic())
    assert presenter.state == 'FAILED' and not presenter.checked
    presenter.request(0)
    ready(window)
    assert presenter.checked


def test_timeout_locks_retries_and_late_reply_is_honest(window):
    presenter = window.presentation
    before = len(window.sent)
    presenter.pending['deadline'] = 0
    presenter.tick()
    assert presenter.state == 'TIMEOUT'
    presenter.request(2)
    assert len(window.sent) == before
    ready(window)
    assert presenter.state == 'READY'


def test_mouse_keyboard_and_page_pen_share_dispatch(window):
    app = QtWidgets.QApplication.instance()
    ready(window)
    QTest.mouseClick(window.presentation.buttons[2], QtCore.Qt.MouseButton.LeftButton)
    assert window.sent[-1][2] == {'id': 'fm'}
    ready(window, 'fm')
    window.activateWindow()
    app.processEvents()
    QTest.keyClick(window, QtCore.Qt.Key.Key_PageDown)
    assert window.sent[-1][2] == {'id': 'listen'}
    ready(window, 'listen')
    assert window.active_page == 2
    QTest.keyClick(window, QtCore.Qt.Key.Key_7)
    assert window.sent[-1][2] == {'id': 'perf'}
    ready(window, 'perf')
    assert window.active_page == 5
    QTest.keyClick(window, QtCore.Qt.Key.Key_Escape)
    assert window.sent[-1][1] == 'stop'


def test_no_live_command_during_replay_or_stale_connection(window):
    ready(window)
    window.worker.session = 'recording.zsr'
    count = len(window.sent)
    window.presentation.request(2)
    assert len(window.sent) == count
    window.worker.session = None
    window.last_packet_time = 0
    window.presentation.request(2)
    assert len(window.sent) == count


def test_service_reconnect_invalidates_precheck_and_pending(window):
    ready(window)
    presenter = window.presentation
    presenter.request(2)
    old_seq = presenter.pending['seq']
    presenter.packet(dict(type='hello'), time.monotonic())
    assert not presenter.checked and presenter.pending['seq'] != old_seq
    assert presenter.pending['scene'] == 'check'
    assert presenter.state == 'STARTING'


def test_clock_uses_elapsed_monotonic_time_not_timer_tick_counts(window):
    presenter = window.presentation
    presenter.started = presenter.segment_started = 10
    presenter.clock = lambda: 251.9
    presenter.tick()
    assert '04:01' in presenter.times.text()
    assert '#FF5A5A' in presenter.times.styleSheet()


def test_receiver_sequence_is_assigned_before_socket_sends():
    receiver = Receiver(address='192.0.2.1')
    assert receiver.command('scene', id='fm') == 1
    assert receiver.command('scene', id='listen') == 2
    assert receiver.requests.get_nowait() == (1, 'scene', {'id': 'fm'})
    assert Receiver(session='test.zsr').command('stop') is None


def test_fallback_missing_is_disabled_and_cannot_silently_substitute(window):
    presenter = window.presentation
    ready(window)
    assert not presenter.fallback.isEnabled()
    count = len(window.sent)
    presenter.play_fallback()
    assert len(window.sent) == count
    assert '尚未注册' in presenter.banner.text()


def test_replay_checks_manifest_and_waits_for_idle_confirmation(window, tmp_path, monkeypatch):
    from sentinel_host import presentation
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    path = tmp_path/'fallback.zsr'
    recorder = Recorder(path)
    recorder.append(dict(type='hello', len=0, seq=0, t_mono=0, mode='monitor'))
    recorder.close()
    presenter = window.presentation
    presenter.scenes[0]['fallback'] = 'fallback.zsr'
    ready(window)
    calls = []
    window.start_worker = lambda **kwargs: calls.append(kwargs)
    presenter.play_fallback()
    assert not calls and window.sent[-1][2] == {'id': 'idle'}
    ready(window, 'idle')
    presenter.tick()
    assert calls == [dict(session=str(path))]
    assert presenter.state == 'REPLAY'
    assert 'REPLAY' in presenter.banner.text()


def test_stop_cancels_deferred_replay(window):
    ready(window)
    window.presentation._fallback_after_idle = Path('test.zsr')
    window.presentation.stop()
    assert window.presentation._fallback_after_idle is None


def test_config_has_only_verified_station_and_honest_notes():
    value = load_scenes()
    assert value['scenes'][3]['station_mhz'] == 95.8
    assert not value['scenes'][5]['available']
    assert '未经概率校准' in value['scenes'][2]['notes']
