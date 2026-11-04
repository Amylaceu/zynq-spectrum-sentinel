"""Regression: default restoration must release audio pins, not just EN."""
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'src/ps'))
from sentinel.app.features_j6 import FeatureBackend
from sentinel.drivers.regs import spec_ctrl as F, src_ctrl as S
import pytest


def test_audio_pin_configuration_is_cleared_before_default_readback(monkeypatch):
    events = []
    class Registers:
        def read(self, offset):
            values = {S.RATE_DIV: round(100000000*65536/3840000), S.FRAME_LIMIT: 0,
                S.FCW0: 64*2097152, S.FCW1: 0, S.FCW2: 0, S.AMP0: 8192, S.AMP1: 0, S.AMP2: 0}
            return values.get(offset, 0)
    class Audio:
        def disable(self, release_pins=False): events.append(('audio', release_pins))
    backend = FeatureBackend.__new__(FeatureBackend)
    backend.hw = SimpleNamespace(audio=Audio(), source=SimpleNamespace(stop=lambda: events.append('stop'), configure=lambda *a, **kw: None),
        lcd=SimpleNamespace(enable=lambda flag: None), src_regs=Registers())
    backend.radio = None; backend.config = {'lo_hz': 96050000}
    backend.mute = lambda: events.append('mute')
    backend.readback = lambda: dict(source_ctrl=0, spec_ctrl=1, average_shift=3, noise_amplitude=0,
        cfar_ctrl=1, alpha=1974, audio_control=0, codec_muted=True, lcd_enabled=False)
    monkeypatch.setattr('sentinel.app.features_j6.configure_checked', lambda *a: events.append('checked'))
    value = backend.restore()
    assert events[:3] == ['mute', ('audio', True), 'stop']
    assert value['source_defaults_checked'] and backend.active is None


def test_replay_reset_is_restarted_before_fm_quality(monkeypatch):
    events = []
    receiver = SimpleNamespace(running=False, start=lambda: events.append('start'))
    capture = SimpleNamespace(failed=False, engine=SimpleNamespace(inflight=[], dma=SimpleNamespace(recvchannel=receiver)))
    backend = FeatureBackend.__new__(FeatureBackend)
    backend.hw = SimpleNamespace(channel_capture=capture)
    backend.replay_reset_since_capture = True
    monkeypatch.setattr('sentinel.app.resident.ReceiveBackend._quality', lambda self: events.append('quality'))
    backend._quality()
    assert events == ['start', 'quality'] and not backend.replay_reset_since_capture


def test_failed_dma_is_never_rearmed_for_audio():
    backend = FeatureBackend.__new__(FeatureBackend)
    backend.hw = SimpleNamespace(channel_capture=SimpleNamespace(failed=True, engine=SimpleNamespace(inflight=[])))
    backend.replay_reset_since_capture = True
    with pytest.raises(RuntimeError, match='failed or owned'):
        backend._quality()
