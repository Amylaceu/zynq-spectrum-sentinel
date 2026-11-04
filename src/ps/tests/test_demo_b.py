import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sentinel.app.demo_b import prepare_performance, stop_transmit_path


class Register:
    def __init__(self, events, name, value=0):
        self.events, self.name, self.values = events, name, {0: value}

    def write(self, offset, value):
        self.events.append((self.name, offset, value))
        self.values[offset] = value

    def read(self, offset):
        return self.values.get(offset, 0)


class Tx:
    def __init__(self, events, inflight=False):
        self.events, self.inflight = events, inflight

    def stop(self, timeout_s):
        self.events.append(('tx_stop', timeout_s))
        self.inflight = False


class Radio:
    def __init__(self, events, mute_error=False):
        self.events, self.mute_error = events, mute_error
        self.lib = self
        self.mode = 2

    def mute(self):
        self.events.append(('mute',))
        if self.mute_error:
            raise RuntimeError('mute failed')

    def stop(self):
        self.events.append(('rf_stop',))

    def close(self):
        self.events.append(('close',))

    @property
    def tx_atten(self):
        return (89.75, 89.75)

    @staticmethod
    def _check(code, label):
        if code:
            raise RuntimeError(label)

    def z20_get_ensm_mode(self, mode):
        mode._obj.value = self.mode
        return 0


class HW:
    def __init__(self, events):
        self.events = events
        self.src_regs = Register(events, 'src')
        self.src_regs.write(0x20, 32768)
        self.src_regs.write(0, 1)
        self.checked = self
        self.audio = type('Audio', (), {'control': Register(events, 'audio')})()
        self.channel_capture = type('Capture', (), {
            'engine': type('Engine', (), {'inflight': []})()})()

    def registers(self, name):
        return Register(self.events, name)


class Perf:
    def __init__(self, events, status=0):
        self.events, self.status = events, status

    def clear(self):
        self.events.append(('perf_clear',))
        self.status = 0

    def snapshot(self):
        self.events.append(('perf_snapshot',))
        return type('Snapshot', (), {'status': self.status})()

    def arm(self):
        self.events.append(('perf_arm',))


def test_performance_segment_clears_startup_fault_before_arming():
    events = []
    hw = HW(events)
    hw.src_regs.values[0] = 0
    hw.perf = Perf(events, status=1)
    hw.reset_channelizer = lambda: events.append(('reset_channelizer',))

    result = prepare_performance(hw)

    assert result == {'frozen_image_reloaded': True, 'initial_status': 0}
    assert [event[0] for event in events[-4:]] == [
        'reset_channelizer', 'perf_clear', 'perf_snapshot', 'perf_arm']


def test_performance_never_clears_a_running_measurement():
    events = []
    hw = HW(events)
    events.clear()
    with pytest.raises(RuntimeError, match='Stop the source'):
        prepare_performance(hw)
    assert not events


@pytest.mark.parametrize('persistent', [False, True])
def test_internal_segment_reloads_frozen_image_and_stops_before_unlock(tmp_path, monkeypatch, persistent):
    from types import SimpleNamespace
    from sentinel.app import demo_b as module
    events = []
    hw = HW(events)
    hw.audio.disable = lambda **kwargs: None
    hw.enable_processing = lambda **kwargs: None
    hw.lcd = SimpleNamespace(set_bus_phase=lambda n: None, enable=lambda: None)
    hw.source = SimpleNamespace(configure=lambda *args, **kwargs: None,
                                start=lambda: hw.src_regs.write(0, 5))
    class FakeSession:
        def __init__(self, bit, source, load, *args, **kwargs):
            assert source=='test' and load is True
        def __enter__(self):
            return SimpleNamespace(hw=hw)
        def __exit__(self, *args):
            assert hw.src_regs.read(0)==0
            assert hw.src_regs.read(0x20)==0
            events.append(('unlock',))
    class BrokenDisplay:
        def __init__(self,*args, **kwargs):
            raise RuntimeError('render failed')
    monkeypatch.setattr(module, 'Session', FakeSession)
    monkeypatch.setattr(module, 'prepare_performance', lambda hw, **kwargs: {})
    monkeypatch.setattr(module, 'Display', BrokenDisplay)
    record = {}
    with pytest.raises(RuntimeError, match='render failed'):
        runtime = (SimpleNamespace(session=FakeSession, wait_frames=lambda hw: None,
                                   mark_content_started=lambda: None) if persistent else None)
        module.receive_segment(tmp_path, 'frozen.bit', tmp_path, 15, record,
                               performance=True, runtime=runtime)
    assert record['source_after_stop']==0
    assert events[-1]==('unlock',)


def test_safe_stop_mutes_and_reads_back_every_control():
    events = []
    hw, radio, tx = HW(events), Radio(events), Tx(events, inflight=True)

    readback, errors = stop_transmit_path(radio, tx, hw)

    assert errors == []
    assert readback == dict(ensm=2, tx_attenuation_db=[89.75, 89.75], gpio_data=0,
                            source_ctrl=0, noise_amplitude=0, audio_control=0)
    assert [event[0] for event in events[-6:]] == [
        'mute', 'tx_stop', 'src', 'src', 'rf_stop', 'close']
    assert not tx.inflight


def test_cleanup_continues_to_rf_stop_when_mute_fails():
    events = []
    hw, radio, tx = HW(events), Radio(events, mute_error=True), Tx(events)

    readback, errors = stop_transmit_path(radio, tx, hw)

    assert any(error.startswith('mute:') for error in errors)
    assert ('rf_stop',) in events
    assert ('close',) in events
    assert readback['ensm'] == 2
    assert readback['tx_attenuation_db'] == [89.75, 89.75]


def test_failed_open_does_not_write_any_registers():
    events = []
    hw = HW(events)
    events.clear()
    assert stop_transmit_path(None, None, hw) == ({}, [])
    assert events == []


def test_ensm_readback_error_is_preserved_and_close_still_runs():
    events = []
    hw, radio = HW(events), Radio(events)
    radio.mode = 10
    readback, errors = stop_transmit_path(radio, Tx(events), hw)
    assert readback['ensm'] == 10
    assert any(error.startswith('rf_readback:') for error in errors)
    assert ('close',) in events


def test_failed_dma_drain_still_closes_rf_and_records_error():
    events = []
    class FailedTx(Tx):
        def stop(self, timeout_s):
            raise TimeoutError('still inflight')
    hw, radio, tx = HW(events), Radio(events), FailedTx(events, inflight=True)
    readback, errors = stop_transmit_path(radio, tx, hw)
    assert tx.inflight
    assert any(error.startswith('tx_dma_stop:') for error in errors)
    assert ('rf_stop',) in events and ('close',) in events
    assert readback['source_ctrl'] == 0
