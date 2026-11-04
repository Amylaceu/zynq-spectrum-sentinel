"""F1 release invariants exercised on a PC without PYNQ or RF access."""
import ctypes
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.ps.sentinel.release_support import load_config, NoiseRecorder, verify_release, write_result
from src.ps.sentinel.audio_y3 import CodecOutputs
from src.ps.tests.test_audio_y3 import Bus

ROOT = Path(__file__).resolve().parents[3]


def config_file(tmp_path, **changes):
    value = json.loads((ROOT/'board/release/config.yaml').read_text())
    value.update(changes)
    p = tmp_path/'config.yaml'
    p.write_text(json.dumps(value))
    return p


@pytest.mark.parametrize('volume,code', [(-45, 0), (-21, 16), (-15, 20), (-12, 22), (-9, 24), (-6, 26)])
def test_output_range_and_register_readback(volume, code):
    bus = Bus()
    codec = CodecOutputs(bus, delay=lambda _: None)
    codec.initialize(volume_db=volume)
    assert all(bus.regs[r] == code for r in (0x2e, 0x2f, 0x30, 0x31))
    assert bus.regs[0x19] == codec.MUTE
    codec.unmute()
    assert codec.shutdown() == []
    assert bus.regs[0x19] == codec.MUTE and bus.regs[4] == 0xc0


@pytest.mark.parametrize('volume', [-4.5, 0, -46.5, -12.1, float('nan'), float('inf'), True, '-12'])
def test_rejects_volume_before_hardware_writes(volume):
    bus = Bus()
    with pytest.raises(ValueError):
        CodecOutputs(bus, delay=lambda _: None).initialize(volume_db=volume)
    assert bus.writes == []


def test_explicit_speaker_gain_keeps_line_out_ceiling():
    bus = Bus()
    codec = CodecOutputs(bus, delay=lambda _: None)
    codec.initialize(volume_db=-6, speaker_volume_db=0)
    assert all(bus.regs[r] == 26 for r in (0x2e, 0x2f, 0x30))
    assert bus.regs[0x31] == 30
    codec.unmute()
    assert codec.assert_safe()


@pytest.mark.parametrize('volume', [1.5, 4.5, 0.1, float('nan'), True])
def test_speaker_positive_gain_rejected_before_writes(volume):
    bus = Bus()
    with pytest.raises(ValueError):
        CodecOutputs(bus, delay=lambda _: None).initialize(volume_db=-6, speaker_volume_db=volume)
    assert bus.writes == []


@pytest.mark.parametrize('changes', [dict(sample_rate_hz=30720000), dict(bus_phase=3),
    dict(max_volume_db=0), dict(volume_db=-4.5), dict(autostart=True),
    dict(tx_attenuation_db=30), dict(pilot_min_db=14), dict(run_seconds=float('nan')),
    dict(station_hz=100000000), dict(image='sentinel_v1d'),
    dict(speaker_volume_db=1.5), dict(speaker_max_volume_db=4.5)])
def test_frozen_config_rejects_unsafe_or_unverified_settings(tmp_path, changes):
    with pytest.raises(ValueError):
        load_config(config_file(tmp_path, **changes))


def test_release_defaults_match_explicit_user_plan(tmp_path):
    config = load_config(config_file(tmp_path))
    assert config['volume_db'] == -6 and config['max_volume_db'] == -6
    assert config['speaker_volume_db'] == 0 and config['speaker_max_volume_db'] == 0
    assert config['lo_hz'] == 96050000 and config['station_hz'] == 95800000


def test_noise_evidence_captures_measured_gain_rssi_iq_and_is_rate_limited(tmp_path):
    tick = [1.0]
    calls = []
    def get_gain(channel, pointer):
        calls.append(channel)
        ctypes.cast(pointer, ctypes.POINTER(ctypes.c_int32))[0] = 59
        return 0
    radio = SimpleNamespace(lib=SimpleNamespace(z20_get_rx_gain=get_gain),
        _check=lambda value, label: None if value == 0 else (_ for _ in ()).throw(RuntimeError(label)),
        rssi=lambda _: -64.5, tx_atten=(89.75, 89.75))
    record = NoiseRecorder(tmp_path, clock=lambda: tick[0])
    capture = dict(iq=np.ones(4096, dtype=np.complex64)*.2, timestamp_cycles=123)
    assert record.observe(capture, {'pilot_prominence_db': 21}, radio, 95800000, 96050000) is None
    assert not calls
    event = record.observe(capture, {'pilot_prominence_db': 12}, radio, 95800000, 96050000)
    assert event['rx_gain_db'] == 59 and event['rssi_dbm'] == -64.5
    p = tmp_path/event['iq_file']
    assert hashlib.sha256(p.read_bytes()).hexdigest() == event['iq_sha256']
    with np.load(p) as npz:
        np.testing.assert_array_equal(npz['iq'], capture['iq'])
    tick[0] = 2
    assert record.observe(capture, {'pilot_prominence_db': 10}, radio, 95800000, 96050000) is None
    tick[0] = 12
    assert record.observe(capture, {'pilot_prominence_db': 10}, radio, 95800000, 96050000)
    assert len(list(tmp_path.glob('*.json'))) == 2
    for path in tmp_path.glob('*.sha256'):
        original = Path(str(path)[:-7])
        assert path.read_text().split()[0] == hashlib.sha256(original.read_bytes()).hexdigest()


def test_release_rejects_corruption_and_escaped_path(tmp_path):
    (tmp_path/'config.yaml').write_text('{}')
    manifest = {'files': {'config.yaml': hashlib.sha256(b'{}').hexdigest()}}
    write_result(tmp_path/'manifest.json', manifest)
    verify_release(tmp_path, require_library=False)
    (tmp_path/'config.yaml').write_text('{"changed":true}')
    with pytest.raises(ValueError, match='digest mismatch'):
        verify_release(tmp_path, require_library=False)
    write_result(tmp_path/'manifest.json', {'files': {'../outside': '0'*64}})
    with pytest.raises(ValueError, match='Unsafe'):
        verify_release(tmp_path, require_library=False)


def test_radio_library_path_can_be_local_to_release_without_opening_hardware(monkeypatch):
    from src.ps.sentinel.rf import ad9361
    observed = []
    monkeypatch.setattr(ad9361, 'bind_library', lambda p: observed.append(p) or object())
    monkeypatch.setenv('SENTINEL_RF_LIBRARY', '/release/v2/ps/libad9361_pynq/libad9361_pynq.so')
    ad9361.AD9361()
    assert observed == ['/release/v2/ps/libad9361_pynq/libad9361_pynq.so']


@pytest.mark.parametrize('prominence,good,expected', [
    (35.0, False, False), (19.9, True, False), (20.0, True, True),
])
def test_startup_quality_requires_pilot_and_existing_phase_checks(
        tmp_path, monkeypatch, prominence, good, expected):
    from src.ps.sentinel import release_support as support
    checks = []
    radio = SimpleNamespace(check_rssi=lambda: checks.append('rssi'))
    capture = dict(iq=np.ones(4096, dtype=np.complex64), timestamp_cycles=1)
    hw = SimpleNamespace(channel_capture=SimpleNamespace(acquire=lambda *a, **k: capture))
    monkeypatch.setattr(support, 'stereo_quality', lambda iq: dict(
        pilot_prominence_db=prominence, good=good))
    monkeypatch.setattr(support.NoiseRecorder, 'observe', lambda *a, **k: None)
    result = support.startup_quality(hw, radio, 95800000, 96050000, tmp_path)
    assert result['quality_pass'] is expected
    assert result['pilot_pass'] is (prominence >= 20)
    assert checks == ['rssi', 'rssi']
