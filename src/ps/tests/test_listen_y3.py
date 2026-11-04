"""Exercise audio lifecycle/faults during an independent AMC/RF session."""
from contextlib import ExitStack
from types import SimpleNamespace

import pytest

from src.ps.sentinel.capture_x5 import select_channel
from src.ps.sentinel.listen_y3 import FMListener, validate_listen, evaluate_listening


def rig():
    events, evidence = [], {}
    now = [0.0]
    state = dict(playing=True, enabled=True, fifo_level=4096, frames=0,
                 pcm_samples=0, iq_overflow=False, pcm_full=False, underflows=0)
    def disable(release_pins):
        events.append('pins_off')
        state['underflows'] = 0  # model hardware clearing the sticky latch
    audio = SimpleNamespace(
        disable=disable, start=lambda: events.append('arm'),
        configure=lambda station, lo, codec: select_channel(station-lo),
        snapshot=lambda: dict(state))
    codec = SimpleNamespace(
        initialize=lambda volume_db: events.append(('init', volume_db)),
        unmute=lambda: events.append('unmute'),
        shutdown=lambda: events.append('mute') or [])
    hw = SimpleNamespace(audio=audio, channel_health=lambda: 0,
                         x5_status=SimpleNamespace(read=lambda _: 0))
    def sleep(seconds):
        now[0] += seconds
    listener = FMListener(hw, 95800000, 96400000, evidence, codec=codec,
                          clock=lambda: now[0], sleep=sleep)
    return listener, state, now, events, evidence


def test_amc_error_mutes_before_rf_session_cleanup():
    listener, state, now, events, evidence = rig()
    with pytest.raises(RuntimeError, match='capture failed'):
        with ExitStack() as stack:
            stack.callback(lambda: events.append('rf_stop'))
            stack.enter_context(listener)
            assert 'unmute' not in events
            listener.wait_ready(lambda: events.append('rssi_check'))
            raise RuntimeError('capture failed')
    assert events[-3:] == ['mute', 'pins_off', 'rf_stop']
    assert evidence['status'] == 'failed'
    assert evidence['human_listening'] == 'PENDING'


def test_counter_rates_and_normal_shutdown():
    listener, state, now, events, evidence = rig()
    with listener:
        listener.wait_ready(lambda: None)
        now[0] += 1
        state.update(frames=48000, pcm_samples=48000)
        assert listener.sample()['audio_frame_rate_hz'] == pytest.approx(48000)
    assert evidence['status'] == 'stopped_awaiting_human'
    assert evidence['audio_before_stop']['frames'] == 48000
    assert events[-2:] == ['mute', 'pins_off']


@pytest.mark.parametrize('fault,value', [('underflows', 1), ('iq_overflow', True),
                                      ('pcm_full', True), ('playing', False),
                                      ('fifo_level', 1)])
def test_fault_in_last_fraction_of_second_is_not_erased_by_shutdown(fault, value):
    listener, state, now, events, evidence = rig()
    with pytest.raises(RuntimeError):
        with listener:
            listener.wait_ready(lambda: None)
            state[fault] = value
    assert evidence['last_observed_audio'][fault] == value
    assert evidence['status'] == 'failed'
    assert events[-2:] == ['mute', 'pins_off']


def test_prefill_timeout_keeps_codec_muted_and_releases_pins():
    listener, state, now, events, evidence = rig()
    state.update(playing=False, fifo_level=0)
    with pytest.raises(TimeoutError):
        with listener:
            listener.wait_ready(lambda: None)
    assert 'unmute' not in events
    assert events[-2:] == ['mute', 'pins_off']


def test_failed_initialize_attempts_cleanup_before_enter_returns():
    listener, state, now, events, evidence = rig()
    def broken(volume_db):
        raise IOError('IIC fault')
    listener.codec.initialize = broken
    with pytest.raises(IOError):
        with listener:
            pytest.fail('body must not run')
    assert events[-2:] == ['mute', 'pins_off']
    assert evidence['status'] == 'failed_initialization'


def test_cleanup_failure_cannot_report_success():
    listener, state, now, events, evidence = rig()
    listener.codec.shutdown = lambda: ['codec mute failed']
    with pytest.raises(RuntimeError, match='safe stop'):
        with listener:
            listener.wait_ready(lambda: None)
    assert evidence['status'] == 'failed'
    assert events[-1] == 'pins_off'


def test_counter_stall_is_rejected_even_when_playing_flag_is_set():
    listener, state, now, events, evidence = rig()
    with pytest.raises(RuntimeError, match='counter'):
        with listener:
            listener.wait_ready(lambda: None)
            now[0] += 1
            listener.sample()


@pytest.mark.parametrize('image,station,lo,volume', [
    ('sentinel_v1d', 95800000, 96400000, -21),
    ('sentinel_v2_100m', float('nan'), 96400000, -21),
    ('sentinel_v2_100m', 433920000, 433000000, -21),
    ('sentinel_v2_100m', 95800000, 98000000, -21),
    ('sentinel_v2_100m', 95800000, 96400000, -20),
])
def test_invalid_listening_options_fail_before_hardware(image, station, lo, volume):
    with pytest.raises(ValueError):
        validate_listen(image, station, lo, volume)


def test_legacy_monitor_without_audio_remains_valid():
    validate_listen('sentinel_v1d', None, 98000000, -21)
    validate_listen('sentinel_v2_100m', 95800000, 96400000, -21)


def complete_result():
    audio = dict(playing=True, fifo_level=4096, underflows=0,
                 iq_overflow=False, pcm_full=False)
    sample = dict(interval_s=1, audio_frame_rate_hz=48000,
                  pcm_sample_rate_hz=48000, audio=audio)
    return dict(status='completed', stopped_by_signal=False, elapsed_total_s=30.1,
                audio=dict(status='stopped_awaiting_human', safe_stop_errors=[],
                           samples=[sample.copy() for _ in range(29)],
                           audio_before_stop=audio, channel_health_before_stop=0,
                           pfb_capture_status_before_stop=0),
                telemetry=[dict(display_fps=49, temperature_c=45,
                                rx_rssi_dbm=-50, tx_atten_mdb=[89750, 89750])])


def test_independent_audio_checks_do_not_claim_hearing_or_recognition_accuracy():
    checks = evaluate_listening(complete_result(), 30)
    assert all(checks.values())
    assert 'human_listening' not in checks
    assert 'recognition_accuracy' not in checks


@pytest.mark.parametrize('case', ['missing', 'early', 'last_error', 'slow_display',
                                  'stalled_clock', 'nan_temperature', 'mute_failed'])
def test_independent_evaluation_rejects_incomplete_or_faulty_evidence(case):
    result = complete_result()
    if case == 'missing': result['audio'] = {}
    elif case == 'early': result['stopped_by_signal'] = True
    elif case == 'last_error': result['audio']['audio_before_stop']['underflows'] = 1
    elif case == 'slow_display': result['telemetry'][0]['display_fps'] = 29
    elif case == 'stalled_clock': result['audio']['samples'][2]['audio_frame_rate_hz'] = 0
    elif case == 'nan_temperature': result['telemetry'][0]['temperature_c'] = float('nan')
    elif case == 'mute_failed': result['audio']['safe_stop_errors'] = ['codec mute failed']
    assert not all(evaluate_listening(result, 30).values())
