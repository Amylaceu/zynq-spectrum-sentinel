from pathlib import Path

import pytest

from src.ps.sentinel.app.runtime_v2 import SentinelRuntime


class FakeHardware:
    def __init__(self, bit, download):
        self.downloads = int(download)
        self.overlay = type('Overlay', (), {'is_loaded': lambda self: True})()
        self.channel_capture = type('Capture', (), {'failed': False})()


def test_overlay_and_predictor_are_cached_once(tmp_path):
    model = Path(__file__).parents[1]/'models/weights/amc_v2/round_3/model.npz'
    made = []

    class Predictor:
        def __init__(self, path, precision):
            made.append((path, precision))

        def predict(self, iq, fs):
            assert len(iq) == 4096 and fs == 480000
            return [dict(label='FM')]

    runtime = SentinelRuntime(tmp_path, hw_factory=FakeHardware,
                              predictor_factory=Predictor)
    runtime._hardware(str(runtime.bit), download=False)
    runtime._hardware(str(runtime.bit), download=True)
    first = runtime.predictor(model)
    assert runtime.predictor(model) is first
    assert runtime.evidence['overlay_loads'] == 1
    assert runtime.evidence['model_loads'] == 1
    assert runtime.evidence['model_warmups'] == 1
    assert runtime.evidence['warmup_source'].startswith('synthetic')
    assert len(made) == 1


def test_failed_capture_marks_runtime_unusable(tmp_path):
    runtime = SentinelRuntime(tmp_path, hw_factory=FakeHardware)
    runtime.hw = FakeHardware(str(runtime.bit), False)
    runtime.hw.channel_capture.failed = True
    with pytest.raises(RuntimeError, match='full PL recovery'):
        runtime._hardware(str(runtime.bit))
    with pytest.raises(RuntimeError, match='failed'):
        runtime._hardware(str(runtime.bit))


def test_segment_cleanup_verifies_and_poison_on_failure(tmp_path, monkeypatch):
    import src.ps.sentinel.audio_y3 as audio

    runtime = SentinelRuntime(tmp_path)
    runtime.stopped_readback = lambda: {'status': 'PASS', 'gpio_data': 0,
                                        'source_ctrl': 0, 'audio_control': 0}
    runtime.session_factory = lambda *args, **kwargs: type('Inner', (), {
        'hw': type('HW', (), {
            'source': type('Source', (), {'stop': lambda self: None})(),
            'src_regs': type('Regs', (), {'write': lambda self, *args: None})(),
            'audio': type('Audio', (), {'control': type('Control', (), {'read': lambda self, _: 0})(),
                                        'disable': lambda self, **kwargs: None})(),
        })(), 'radio': type('Radio', (), {'tx_atten': (89.75, 89.75)})(),
        'rf_gpio': object(), '__enter__': lambda self: self,
        'close': lambda self: None,
    })()
    monkeypatch.setattr(audio, 'shutdown_audio_outputs', lambda codec, device: [])
    segment = runtime.session(str(runtime.bit), 'rf')
    with segment:
        pass
    assert segment.record['stop_readback']['status'] == 'PASS'
    assert segment.record['tx_attenuation_before_reset_db'] == [89.75, 89.75]
    assert runtime.evidence['rf_initializations'] == 1
    assert not runtime.poisoned

    runtime.session_factory = lambda *args, **kwargs: type('Broken', (), {
        '__enter__': lambda self: (_ for _ in ()).throw(RuntimeError('init failed')),
        'close': lambda self: None,
    })()
    with pytest.raises(RuntimeError, match='init failed'):
        with runtime.session(str(runtime.bit), 'test'):
            pass
    assert runtime.poisoned


def test_wait_frames_handles_wrap_and_rejects_stalled_display(tmp_path):
    from types import SimpleNamespace
    ticks = [0.0]
    frames = iter([0xffffffff, 0, 1])
    hw = SimpleNamespace(lcd=SimpleNamespace(registers=SimpleNamespace(
        read=lambda _: next(frames))))
    runtime = SentinelRuntime(tmp_path, clock=lambda: ticks[0],
                              sleep=lambda step: ticks.__setitem__(0, ticks[0]+step))
    assert runtime.wait_frames(hw) == 1
    hw.lcd.registers.read = lambda _: 5
    with pytest.raises(TimeoutError, match='two'):
        runtime.wait_frames(hw, timeout=.03)
    runtime.stop_requested = True
    with pytest.raises(KeyboardInterrupt):
        runtime.wait_frames(hw)


def test_cached_script_logs_exception_and_restores_stop_handler(tmp_path):
    import signal
    from types import SimpleNamespace
    runtime = SentinelRuntime(tmp_path)
    handler = signal.getsignal(signal.SIGTERM)

    def fail(argv, runtime):
        signal.signal(signal.SIGTERM, lambda *_: None)
        raise RuntimeError('injected segment fault')

    runtime.modules['failure.py'] = SimpleNamespace(main=fail)
    log = tmp_path/'failure.log'
    with pytest.raises(RuntimeError, match='injected segment fault'):
        runtime.run_script('failure.py', [], log)
    assert signal.getsignal(signal.SIGTERM) is handler
    assert 'injected segment fault' in log.read_text()
    assert runtime.poisoned
