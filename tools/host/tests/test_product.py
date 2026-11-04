"""Product navigation and command ownership, including stale and failed replies."""
import hashlib
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT/'tools/host'), str(ROOT/'src/ps')]

import pytest
from PySide6 import QtGui, QtWidgets
from sentinel_host.live_catalog import FEATURES, BY_KEY, PAGES, executable
from sentinel_host.product import Window
from sentinel_host.evidence import record_file


@pytest.fixture
def window():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    value = Window()
    value.timer.stop()
    value.show()
    app.processEvents()
    value.sent = []
    def command(name, **args):
        value.sent.append((name, args))
        return len(value.sent)
    value.worker = SimpleNamespace(session=None, command=command)
    value.model.hello = dict(mode='resident')
    value.last_packet_time = time.monotonic()
    try:
        yield value
    finally:
        value.worker = None
        value.close()
        app.processEvents()


def response(window, scene, *, seq=None, ready=True):
    window.packet(dict(type='reply', ok=True, request_seq=seq or window.pending_scene['seq'],
                       scene=dict(status='READY' if ready else 'NOT_READY', scene=scene,
                                  readiness=dict(ready=ready))), b'', time.monotonic())


def test_all_root_numbers_and_subitems_are_addressable():
    expected = {str(i) for i in range(1, 49)} | {'49'+c for c in 'abcdefg'} | {'50', '51'} | {'52'+c for c in 'abcdef'}
    assert set(BY_KEY) == expected
    assert len(FEATURES) == 63
    assert len(PAGES) == 10


def test_one_press_dispatches_each_installed_scene_and_hides_unavailable_routes(window):
    assert len(window.buttons) == 4
    assert not hasattr(window, 'feature_list')
    assert not hasattr(window, 'catalog_page')
    assert [button.text().split('  ', 1)[1] for button in window.buttons] == [
        '系统自检', '监测识别', '广播收听', '性能监测']
    for index, (_, scene, page, _) in enumerate(window.live_actions):
        window.run_live_action(index)
        assert window.active_page == page
        assert window.pending_scene['scene'] == scene
        window.pending_scene = None
    assert [value for name, value in window.sent] == [
        dict(id='check'), dict(id='fm'), dict(id='listen'), dict(id='perf')]


def test_live_scene_replies_require_matching_seq_scene_and_readiness(window):
    window.jump_feature('14')
    window.activate_feature()
    assert window.sent == [('scene', dict(id='fm'))]
    response(window, 'fm', seq=99)
    assert window.pending_scene is not None
    response(window, 'fm')
    assert window.pending_scene is None
    assert window.current_scene == 'fm'
    assert len(window.scene_records) == 1


@pytest.mark.parametrize('mode,age,preview', [('resident', 10, False), ('monitor', 0, False), ('resident', 0, True)])
def test_stale_legacy_or_synthetic_data_cannot_start_scene(window, mode, age, preview):
    window.model.hello = dict(mode=mode)
    window.last_packet_time = time.monotonic()-age
    window.preview_mode = preview
    window.start_scene('listen')
    assert not window.sent


def test_pending_request_cannot_be_double_started_and_stop_supersedes(window):
    window.start_scene('listen')
    window.start_scene('check')
    assert len(window.sent) == 1
    window.all_stop()
    assert window.sent[-1] == ('scene', dict(id='idle'))
    response(window, 'listen', seq=1)
    assert window.pending_scene['scene'] == 'idle'
    response(window, 'idle')
    assert window.current_scene == 'idle'


def test_not_ready_is_failure_not_running(window):
    window.start_scene('listen')
    response(window, 'listen', ready=False)
    assert window.pending_scene is None
    assert window.current_scene != 'listen'
    assert '失败' in window.action_state.text()


@pytest.mark.parametrize('scene', ['ota', 'noise', 'tx_dloop', 'tune', '../listen'])
def test_unsupported_or_transmit_scene_is_never_enqueued(window, scene):
    with pytest.raises(ValueError):
        window.start_scene(scene)
    assert not window.sent


def test_hotspot_and_timing_limitations_remain_visible(window):
    assert not any('热点' in button.text() or '空口' in button.text()
                   for button in window.buttons)


def test_native_evidence_digest_does_not_fabricate_measurement_date(tmp_path):
    path = tmp_path/'result.json'
    path.write_text('{"status":"FAIL"}', encoding='utf-8')
    record = record_file(path, tmp_path)
    assert '未记录' in record['original_date']
    assert record['integrity'] == 'CURRENT_SNAPSHOT_HASH_ONLY'
    Path(str(path)+'.sha256').write_text(record['sha256']+'  result.json\n')
    assert record_file(path, tmp_path)['integrity'] == 'ORIGINAL_SIDECAR_MATCH'
    path.write_text('{"status":"PASS"}', encoding='utf-8')
    assert record_file(path, tmp_path)['integrity'] == 'HASH_MISMATCH'


def test_failed_reply_never_falls_back_to_recording(window):
    window.start_scene('idle')
    response(window, 'idle', ready=False)
    assert not hasattr(window, '_replay_after_idle')
    assert window.worker.session is None


def test_recorded_session_is_refused_without_touching_live_connection(window):
    worker = window.worker
    for operation in (lambda: window.open_session('verified.zsr'),
                      lambda: window.start_worker(session='verified.zsr')):
        with pytest.raises(ValueError, match='recorded sessions'):
            operation()
    window.replay()
    window.fallback()
    assert window.worker is worker
    assert not window.sent


def test_no_playback_routes_or_historical_source_loaders(window):
    assert '回放中心' not in PAGES
    assert not hasattr(window, 'fallback_button')
    assert all('回放' not in action.text() for action in window.tools_menu().actions())
    assert not hasattr(window, 'feature_list')
    assert not hasattr(window, 'catalog_page')
    assert all(not feature.sources for feature in FEATURES)
    assert all(not window.feature_files(feature) for feature in FEATURES)
    window.load_reference_panorama()
    assert not window.sent


def test_disconnect_and_heartbeat_do_not_display_old_measurements(window):
    window._received_by_type = dict(telemetry=time.monotonic()-10, spectrum=time.monotonic()-10)
    window.model.telemetry.append((0, dict(temperature_c=55, display_fps=40)))
    window.last_packet_time = time.monotonic()  # Fresh heartbeat, stale measurements.
    window._refresh_detail_at = 0
    window.refresh()
    assert window.twin_canvas.isHidden()
    assert all(label.text() == '—' for label in window.kpis)


def test_stale_connection_cannot_export_or_record(window, monkeypatch):
    window.last_packet_time = time.monotonic()-10
    def forbidden(*args, **kwargs):
        raise AssertionError('File dialog must not open for stale data')
    monkeypatch.setattr(QtWidgets.QFileDialog, 'getSaveFileName', forbidden)
    for operation in (window.record, window.export_iq, window.export_csv, window.export_html):
        operation()
    assert not window.sent


def test_close_waits_for_board_idle_ack_not_just_enqueued_stop(window):
    event = QtGui.QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()
    assert window._close_after_idle
    assert not window._idle_confirmed_for_close
    assert window.sent == [('scene', dict(id='idle'))]
    response(window, 'idle', ready=False)
    assert not window._idle_confirmed_for_close
    assert not window._close_after_idle


def test_close_confirms_only_matching_idle_reply(window, monkeypatch):
    event = QtGui.QCloseEvent()
    window.closeEvent(event)
    response(window, 'idle', seq=99)
    assert not window._idle_confirmed_for_close
    response(window, 'idle')
    assert window._idle_confirmed_for_close
    # The scheduled close now uses the normal offline teardown in this fixture.
    monkeypatch.setattr(window, 'stop_worker', lambda: setattr(window, 'worker', None))
    QtWidgets.QApplication.processEvents()
