"""F1 payload and entrypoint compatibility; no board processes are created."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'src/ps'))
sys.path.insert(0, str(ROOT/'tools'))
import release_board


def entry():
    spec = importlib.util.spec_from_file_location('f1_entry_test', ROOT/'board/scripts/release_entry.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_payload_keeps_frozen_image_and_python38_syntax():
    files = release_board.payload_files()
    assert 'scripts/sentinel.sh' in files and 'config.yaml' in files
    assert [n for n in files if n.endswith('.so')] == ['ps/libad9361_pynq/libad9361_f3.so']
    for name, path in files.items():
        if path.suffix == '.py':
            ast.parse(path.read_text(encoding='utf-8'), feature_version=(3, 8))
    assert 'overlay/sentinel_v2_100m/sentinel_v2_100m.bit' in files


@pytest.mark.parametrize('command', ['monitor', 'listen', 'selftest', 'demo'])
def test_release_commands_use_local_files_and_expected_parameters(tmp_path, command):
    mod = entry()
    config = json.loads((ROOT/'board/release/config.yaml').read_text())
    args = SimpleNamespace(command=command, station_mhz=95.8, segment=None, loop=False)
    cmd = mod.worker_command(tmp_path, config, args, tmp_path/'measurements/new')
    assert str(tmp_path/'scripts') in cmd[2]
    if command in ('monitor', 'listen'):
        assert cmd[cmd.index('--bus-phase')+1] == '2'
        assert 'sentinel_v2_100m' in cmd
    if command == 'listen':
        assert cmd[cmd.index('--volume')+1] == '-6'
        assert cmd[cmd.index('--speaker-volume')+1] == '0'
        assert '--stereo-quality-gate' in cmd
        assert cmd[cmd.index('--lo-hz')+1] == '96050000'
    if command == 'demo':
        assert cmd[cmd.index('--volume')+1] == '-6'
        assert cmd[cmd.index('--station-hz')+1] == '95800000'


def test_unconfirmed_station_and_group_b_fail_before_launch(tmp_path):
    mod = entry()
    config = json.loads((ROOT/'board/release/config.yaml').read_text())
    with pytest.raises(ValueError):
        mod.worker_command(tmp_path, config, SimpleNamespace(command='listen', station_mhz=99), tmp_path/'out')
    with pytest.raises(ValueError, match='confirmation'):
        mod.worker_command(tmp_path, config, SimpleNamespace(command='demo', group='B'), tmp_path/'out')


def test_demo_b_explicit_confirmation_and_segment_forwarding(tmp_path):
    mod = entry()
    config = json.loads((ROOT/'board/release/config.yaml').read_text())
    args = SimpleNamespace(command='demo', group='B', antenna_confirmed='yes',
                           segment=6, loop=False, cycles=3)
    command = mod.worker_command(tmp_path, config, args, tmp_path/'out')
    assert command[2] == str(tmp_path/'scripts/demo_b.py')
    assert command[command.index('--antenna-confirmed')+1] == 'yes'
    assert command[command.index('--segment')+1] == '6'
    assert command[command.index('--cycles')+1] == '3'
    args.segment = 4
    with pytest.raises(ValueError, match='B segments'):
        mod.worker_command(tmp_path, config, args, tmp_path/'out')


def test_demo_a_has_fixed_bounded_segments_and_package_scripts():
    from sentinel.app import demo as module
    assert module.SEGMENTS == (
        (1, 'SELFTEST', 10), (2, 'FM MONITOR / AMC', 40),
        (3, 'FM SPEAKER', 30), (4, 'THREE-TONE TEST', 15))
    payload = release_board.payload_files()
    assert 'scripts/demo_a.py' in payload
    assert 'scripts/run_test_display.py' in payload


def test_stale_process_never_authorizes_signaling(tmp_path):
    mod = entry()
    assert not mod.valid_supervisor({'pid': 1, 'root': str(tmp_path), 'start_ticks': '0'}, tmp_path)
    assert not mod.valid_supervisor({'pid': 999999999, 'root': str(tmp_path), 'start_ticks': '0'}, tmp_path)


@pytest.mark.parametrize('change', [
    {}, {'gpio_data': 1}, {'source_ctrl': 2}, {'audio_control': 4},
    {'source_ctrl': None}, {'gpio_data': False}, {'status': 'FAIL'},
])
def test_stop_requires_safe_control_readbacks(tmp_path, monkeypatch, change):
    mod = entry()
    record = dict(status='PASS', gpio_data=0, source_ctrl=0, audio_control=0)
    record.update(change)
    monkeypatch.setattr(mod.subprocess, 'run', lambda *a, **k: SimpleNamespace(
        returncode=0, stdout=json.dumps(record), stderr=''))
    config = {'image': 'sentinel_v2_100m'}
    if change:
        with pytest.raises(RuntimeError, match='Stop readback'):
            mod.postflight(tmp_path, config)
    else:
        assert mod.postflight(tmp_path, config) == record


def test_deploy_checks_installer_hash_before_remote_install(tmp_path, monkeypatch):
    import x2_transport
    archive = tmp_path/'release.tar.gz'
    archive.write_bytes(b'checked archive')
    installer = ROOT/'board/scripts/install_release.py'
    installer_hash = hashlib.sha256(installer.read_bytes()).hexdigest()
    calls = []

    class FakeTransport:
        target = 'xilinx@board'
        def copy(self, source, destination):
            calls.append(('copy', Path(source).name, destination))
        def ssh(self, command, privileged=False, timeout=60):
            calls.append(('ssh', command, privileged))
            if command[0] == 'sha256sum':
                return installer_hash+'  '+command[1]
            return json.dumps(dict(status='INSTALLED_HASH_VERIFIED',
                                   archive_sha256=archive_hash))

    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    monkeypatch.setattr(x2_transport, 'Transport', FakeTransport)
    result = release_board.deploy(archive)
    assert result['archive_sha256'] == archive_hash
    install_calls = [call for call in calls if call[0] == 'ssh' and call[2]]
    assert len(install_calls) == 1
    assert install_calls[0][1][-1] == archive_hash
    assert Path(str(archive.parent/'deployment.json.sha256')).is_file()


def test_deploy_refuses_remote_install_if_installer_hash_differs(tmp_path, monkeypatch):
    import x2_transport
    archive = tmp_path/'release.tar.gz'
    archive.write_bytes(b'checked archive')
    calls = []

    class FakeTransport:
        target = 'xilinx@board'
        def copy(self, source, destination):
            calls.append(('copy', destination))
        def ssh(self, command, privileged=False, timeout=60):
            calls.append(('ssh', command, privileged))
            return '0'*64+'  '+command[1]

    monkeypatch.setattr(x2_transport, 'Transport', FakeTransport)
    with pytest.raises(ValueError, match='installer checksum'):
        release_board.deploy(archive)
    assert not any(call[0] == 'ssh' and call[2] for call in calls)
