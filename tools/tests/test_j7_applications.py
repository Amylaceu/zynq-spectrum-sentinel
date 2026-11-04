"""Application cancellation, admission and quarantine regression, without RF."""
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'src/ps'))
from sentinel.app.features_apps import ApplicationBackend, qualified, voted
from sentinel.app.hostlink_protocol import validate_command, ProtocolError


@pytest.mark.parametrize('identity,action,hz,antenna,allowed', [
    ('F8', 'search', 0, False, True), ('F8', 'start', 87500000, False, True),
    ('F8', 'start', 108000000, False, True), ('F8', 'start', 108100000, False, False),
    ('F8', 'record', 0, False, True), ('F11', 'record', 0, False, False),
    ('F14', 'start', 0, False, False), ('F14', 'start', 0, True, True),
    ('F14', 'start', 0, 1, False), ('F0', 'start', 0, False, True)])
def test_receive_only_application_admission(identity, action, hz, antenna, allowed):
    header = dict(type='command', seq=1, t_mono=0., len=0, command='application',
        args=dict(id=identity, action=action, station_hz=hz, antenna_2g4=antenna))
    if allowed: assert validate_command(header, 'resident')[0] == 'application'
    else:
        with pytest.raises(ProtocolError): validate_command(header, 'resident')


def test_weak_trial_or_insufficient_fm_disqualifies_station():
    trials = [dict(quality_pass=True, label='FM', confidence=.6) for _ in range(10)]
    assert qualified(trials)
    trials[0]['label'] = 'QPSK'
    assert qualified(trials)
    trials[1]['label'] = 'QPSK'
    assert not qualified(trials)
    trials[1]['label'] = 'FM'; trials[0]['quality_pass'] = False
    assert not qualified(trials)


def test_vote_never_exposes_single_frame_or_low_confidence_label():
    one = dict(label='FM', confidence=.9, top5=[dict(label='FM', score=.9)])
    assert voted([one])['label'] == '?'
    assert voted([one]*5)['label'] == 'FM'
    weak = dict(one, confidence=.49)
    assert voted([weak]*5)['label'] == '?'


def backend_job(tmp_path, run):
    b = ApplicationBackend.__new__(ApplicationBackend)
    b.job = dict(id='F11', action='start'); b.app_started = time.monotonic()
    b.run_id = 'a'*32; b.job_output = tmp_path; b.app_results = []
    b.cancel_requests = []; b.quarantined = None; b.fatal_error = None
    b.run_f11 = run; b.emit = lambda *a, **kw: None
    return b


def test_cancellation_acknowledged_only_after_restoration(tmp_path):
    events = []
    def cancel():
        raise InterruptedError('stop')
    b = backend_job(tmp_path, lambda args: cancel())
    b.cancel_requests = [('client', 1, 'application', {})]
    b.restore = lambda: events.append('restored') or {'source_ctrl': 0}
    b.link = SimpleNamespace(service=SimpleNamespace(reply=lambda *a, **kw: events.append(('reply', kw))))
    b.tick()
    assert events[0] == 'restored'
    assert events[1][1]['feature']['restored'] is True
    assert b.app_results[-1]['status'] == 'CANCELLED'


def test_quarantine_never_restores_or_reports_successful_stop(tmp_path):
    b = backend_job(tmp_path, None)
    def fail(args):
        b.quarantined = object()
        raise RuntimeError('owned DMA')
    b.run_f11 = fail
    b.restore = lambda: pytest.fail('must not retune or release owned DMA')
    replies = []
    b.link = SimpleNamespace(service=SimpleNamespace(reply=lambda *a, **kw: replies.append(kw)))
    b.cancel_requests = [('client', 1, 'application', {})]
    with pytest.raises(RuntimeError, match='quarantine'): b.tick()
    assert replies[0]['feature']['restored'] is False


def test_failed_restore_is_recorded_and_blocks_further_rf(tmp_path):
    b = backend_job(tmp_path, lambda _: dict(status='DONE'))
    def fail(): raise RuntimeError('readback differs')
    b.restore = fail
    with pytest.raises(RuntimeError, match='Baseline restoration failed'): b.tick()
    assert b.app_results[-1]['status'] == 'FAILED'
    assert b.app_results[-1]['restored'] is False


def test_display_scan_tile_stays_below_protocol_budget():
    import json
    import numpy as np
    frequency = np.fft.fftshift(np.fft.fftfreq(4096, 1/30720000))
    valid = np.flatnonzero((abs(frequency) <= 10000000) & (abs(frequency) >= 150000))[::8]
    packet = dict(id='F11', run_id='a'*32, stage='scan_tile', completed=1, total=49,
        frequency_hz=(frequency[valid]+512000000).tolist(), power_db=[-123.456789012345]*len(valid))
    assert len(valid) <= 512 and len(json.dumps(packet).encode()) < 32768


def test_wifi_header_level_uses_frame_window_not_whole_capture():
    import numpy as np
    sys.path.insert(0, str(ROOT/'tools'))
    from j_ssid_decode import beacon_level
    iq = np.zeros(10000, dtype=complex); iq[2000:3000] = 1024
    assert beacon_level(iq, 1000000, .002, .001) == pytest.approx(-6.020599913)
    assert beacon_level(iq, 1000000, .02, .001) is None


def test_wifi_antenna_dialog_requires_matching_stopped_reply():
    sys.path.insert(0, str(ROOT/'tools/host'))
    from product import app_instance
    from sentinel_host.application_v61 import Window
    app = app_instance(); w = Window(ROOT)
    callbacks = []
    w.after_stop = lambda: callbacks.append('dialog')
    w.pending = dict(seq=7, id='F1', action='stop', started=time.monotonic())
    header = dict(type='reply', request_seq=6, ok=True, feature=dict(status='STOPPED', restored=True))
    w.packet(header, b'', time.monotonic()); app.processEvents()
    assert not callbacks
    w.packet(dict(header, request_seq=7), b'', time.monotonic()); app.processEvents()
    assert callbacks == ['dialog']
    w.close(); app.processEvents()


def test_rejected_command_retains_error_and_feature_identity():
    sys.path.insert(0, str(ROOT/'tools/host'))
    from product import app_instance
    from sentinel_host.application_v61 import Window
    app = app_instance(); w = Window(ROOT)
    w.pending = dict(seq=5, id='F8', action='start', started=time.monotonic())
    w.packet(dict(type='error', request_seq=5, ok=False,
        error='Start a quality-approved audible broadcast before recording'), b'', time.monotonic())
    assert w.results[-1]['status'] == 'FAILED'
    assert w.results[-1]['id'] == 'F8'
    assert 'quality-approved' in w.results[-1]['error']
    assert not w.pending and not w.data_errors
    w.close(); app.processEvents()


def test_recording_quality_preserves_samples_without_sd_writes(monkeypatch):
    import numpy as np
    from sentinel.app import monitor_x5
    from sentinel import fm_quality
    capture = dict(iq=np.ones(4096, dtype=complex), timestamp_cycles=123)
    backend = ApplicationBackend.__new__(ApplicationBackend)
    backend.recording = True; backend.record_quality = []; backend.quality_samples = []
    backend.config = dict(station_hz=95800000, lo_hz=96050000); backend.scene = 'listen'
    backend.hw = SimpleNamespace(channel_capture=SimpleNamespace(acquire=lambda *a, **k: capture))
    monkeypatch.setattr(fm_quality, 'stereo_quality', lambda iq: dict(good=True, pilot_prominence_db=30))
    monkeypatch.setattr(monitor_x5, 'save_capture', lambda *a: pytest.fail('SD write during recording'))
    assert backend._quality()['good'] is True
    assert backend.record_quality[0][0] is capture
    assert backend.quality_samples[0]['timestamp_cycles'] == 123
    assert backend.last_quality > 0


def test_failed_recording_is_hidden_and_cannot_issue_commands():
    sys.path.insert(0, str(ROOT/'tools/host'))
    from product import app_instance
    from sentinel_host.application_v61 import Window
    app = app_instance(); w = Window(ROOT)
    commands = []
    w.worker = SimpleNamespace(command=lambda *a, **kw: commands.append(kw))
    for button in w.record_buttons.values():
        assert button.isHidden() and not button.isEnabled()
    w.start_feature('F8', action='record')
    w.stop_recording()
    assert not commands
    assert '未通过' in w.state.text()
    w.worker = None; w.close(); app.processEvents()


def test_wifi_results_hide_empty_plots_and_finish_progress():
    sys.path.insert(0, str(ROOT/'tools/host'))
    from product import app_instance
    from sentinel_host.application_v61 import Window
    app = app_instance(); w = Window(ROOT)
    w.panel_for('F14')
    assert w.plot.isHidden() and w.app_plot.isHidden()
    w.app_identity = 'F14'; w.wifi_started = time.monotonic()-133
    w.wifi_complete(dict(result=dict(status='DECODED_BEACONS', networks=[dict(
        ssid='Zynq', bssid='00:11:22:33:44:55', advertised_channel=4, valid_beacons=8)])))
    assert w.progress_bar.value() == 100
    assert '133' in w.progress_bar.format() and '仍在处理' not in w.progress_bar.format()
    assert w.table.item(1, 2).text().strip() == '8 帧'
    assert not w.ssid_filter.text()
    assert w.app_table.item(0, 0).background().color().name() == '#101e2b'
    assert w.app_table.item(0, 0).toolTip() == 'Zynq'
    w.panel_for('F1'); assert not w.plot.isHidden()
    w.close(); app.processEvents()
