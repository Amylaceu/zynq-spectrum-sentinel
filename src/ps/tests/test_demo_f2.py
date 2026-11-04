"""Exercise demonstration orchestration failures without board hardware."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.ps.sentinel.app import demo
from src.ps.sentinel import release_support
from src.ps.sentinel.lcd_x5 import draw_ui, pack_ui


def test_station_selection_rejects_louder_untrusted_signal(monkeypatch):
    stations = [dict(frequency_hz=f, lo_hz=96050000) for f in (95800000, 95450000)]
    monkeypatch.setattr(release_support, 'startup_quality', lambda h, r, f, lo, d:
        dict(quality_pass=f == 95800000, quality=dict(iq_rms=.1 if f == 95800000 else .8)))
    value = release_support.select_demo_station(None, None, dict(stations=stations, lo_hz=96050000), 'unused')
    assert value['selected']['frequency_hz'] == 95800000
    monkeypatch.setattr(release_support, 'startup_quality', lambda *a:
        dict(quality_pass=False, quality=dict(iq_rms=.8)))
    assert release_support.select_demo_station(None, None,
        dict(stations=stations, lo_hz=96050000), 'unused')['selected'] is None


def test_demo_ui_retains_frozen_palette():
    right, status = draw_ui([], demo_title='2/4 FM MONITOR', demo_remaining_s=39.2,
                            demo_mode='MONITOR', temperature_c=52, frame=900, fps=29)
    assert pack_ui(right, status).size == 10000
    assert right.max() <= 3 and status.max() <= 3
    assert (right[:22] != 0).any() and (status[65:] != 0).any()


@pytest.mark.parametrize('failure', [None, 'exit', 'false_success', 'cleanup', 'silent', 'bad_hash', 'stop'])
@pytest.mark.parametrize('mode', ['full', 'repeat', 'single', 'loop'])
def test_segments_fail_closed_and_preserve_evidence(tmp_path, monkeypatch, failure, mode):
    if failure is not None and mode != 'full':
        pytest.skip('Failure branches are exercised once with the full sequence')
    root = tmp_path/'release'
    root.mkdir()
    (root/'manifest.json').write_text('{}')
    out = tmp_path/'evidence'
    station = dict(frequency_hz=95800000, lo_hz=96050000)
    monkeypatch.setattr(demo, 'verify_release', lambda root: None)
    monkeypatch.setattr(demo, 'load_config', lambda path: dict(station_hz=95800000, lo_hz=96050000, volume_db=-12))
    monkeypatch.setattr(demo.os, 'geteuid', lambda: 0, raising=False)
    signals, launched, postflights = {}, [], []
    monkeypatch.setattr(demo.signal, 'signal', lambda sig, callback: signals.update({sig: callback}))
    extra = {'full': [], 'repeat': ['--cycles', '3'],
             'single': ['--segment', '3'], 'loop': ['--loop']}[mode]
    monkeypatch.setattr(demo.sys, 'argv', ['demo', '--root', str(root), '--output', str(out),
        '--station-hz', '95800000', '--lo-hz', '96050000', '--volume', '-12', '--isolated']+extra)

    class Child:
        def __init__(self, command, **kwargs):
            self.command = command
            self.done = False
            self.stopped = False
            launched.append(command)
        def poll(self):
            return 0 if self.done else None
        def terminate(self):
            self.stopped = True
        def send_signal(self, sig):
            self.stopped = True
        def wait(self, timeout=None):
            directory = Path(self.command[self.command.index('--out')+1])
            assert not directory.exists(), 'The worker must create its own result directory'
            directory.mkdir()
            number = len(launched)
            record = dict(status='PASS', station_selection=dict(selected=station), audible_seconds=29)
            if (failure == 'stop' and number == 2) or (mode == 'loop' and number == 5):
                signals[demo.signal.SIGTERM]()
                assert self.stopped
            if number == 2:
                if failure == 'false_success':
                    record['status'] = 'failed'
                if failure == 'cleanup':
                    record['safe_stop_errors'] = ['codec readback failed']
            if failure == 'silent' and number == 3:
                record['audible_seconds'] = 0
            release_support.write_result(directory/'result.json', record)
            if failure == 'bad_hash' and number == 2:
                (directory/'result.json').write_text('{}')
            self.done = True
            return 1 if failure == 'exit' and number == 2 else 0

    monkeypatch.setattr(demo.subprocess, 'Popen', Child)
    def postflight(root):
        postflights.append(len(launched))
        return dict(status='PASS', gpio_data=0, source_ctrl=0, audio_control=0)
    monkeypatch.setattr(demo, 'stopped_readback', postflight)
    if failure not in (None, 'stop'):
        with pytest.raises(RuntimeError):
            demo.main()
    else:
        assert demo.main() == 0
    result = json.loads((out/'demo.json').read_text())
    assert result['status'] == ('STOPPED' if mode == 'loop' or failure == 'stop' else 'PASS' if failure is None else 'FAIL')
    expected = {'full': 4, 'repeat': 12, 'single': 2, 'loop': 5}[mode]
    assert len(launched) == (expected if failure is None else 3 if failure == 'silent' else 2)
    assert postflights == list(range(1, len(launched)+1))
    assert release_support.sha(out/'demo.json') == (out/'demo.json.sha256').read_text().split()[0]


@pytest.mark.parametrize('stop_at', [None, 2])
def test_default_demo_reuses_runtime_and_reports_unavailable_wav(tmp_path, monkeypatch, stop_at):
    from src.ps.sentinel.app import runtime_v2
    root = tmp_path/'release'
    root.mkdir()
    (root/'manifest.json').write_text('{}')
    out = tmp_path/'evidence'
    station = dict(frequency_hz=95800000, lo_hz=96050000)
    config = dict(station_hz=95800000, lo_hz=96050000, volume_db=-12)
    monkeypatch.setattr(demo, 'verify_release', lambda root: None)
    monkeypatch.setattr(demo, 'load_config', lambda path: config)
    monkeypatch.setattr(demo.os, 'geteuid', lambda: 0, raising=False)
    monkeypatch.setattr(demo.signal, 'signal', lambda *args: None)
    instances = []

    class Runtime:
        def __init__(self, root):
            instances.append(self)
            self.stop_requested = False
            self.evidence = dict(calls=[])

        def run_script(self, name, argv, log):
            self.evidence['calls'].append(name)
            if len(self.evidence['calls']) == stop_at:
                self.stop_requested = True
            directory = Path(argv[argv.index('--out')+1])
            directory.mkdir()
            release_support.write_result(directory/'result.json', dict(
                status='PASS', station_selection=dict(selected=station), audible_seconds=29))
            return 0

        def stopped_readback(self):
            return dict(status='PASS', gpio_data=0, source_ctrl=0, audio_control=0)

        def close(self):
            self.evidence['closed'] = True

    monkeypatch.setattr(runtime_v2, 'SentinelRuntime', Runtime)
    monkeypatch.setattr(demo.subprocess, 'Popen', lambda *a, **k: pytest.fail('No segment subprocess'))
    wav = tmp_path/'actual_playback.wav'
    assert demo.main(['--root', str(root), '--output', str(out), '--station-hz', '95800000',
                      '--lo-hz', '96050000', '--volume', '-12', '--cycles', '3',
                      '--record-audio', str(wav)]) == 0
    result = json.loads((out/'demo.json').read_text())
    assert len(instances) == 1
    assert len(instances[0].evidence['calls']) == (12 if stop_at is None else stop_at)
    assert result['runtime_mode'] == 'persistent'
    assert result['completed_cycles'] == (3 if stop_at is None else 0)
    assert result['status'] == ('PASS' if stop_at is None else 'STOPPED')
    assert result['final_stop_readback']['status'] == 'PASS'
    assert result['wav_recording']['status'] == 'UNSUPPORTED_NO_PLAYBACK_PCM_READBACK'
    assert not wav.exists()
