"""Y3 acceptance must reject discontinuities and incomplete/unsafe runs."""
import copy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_y3_board as runner


def completed():
    sample = dict(audio=dict(iq_overflow=False, pcm_full=False, underflows=0,
                             playing=True), display_fps=49,
                  tx_attenuation_db=[89.75, 89.75], rx_rssi_dbm=-50,
                  audio_frame_rate_hz=48000, pcm_sample_rate_hz=48000,
                  channel_health=0, pfb_capture_status=0, temperature_c=45)
    result = dict(status='completed', elapsed_total_s=300.1,
                  samples=[copy.deepcopy(sample) for _ in range(297)],
                  audio_before_stop=copy.deepcopy(sample['audio']),
                  channel_health_before_stop=0, pfb_capture_status_before_stop=0,
                  final_codec_muted=True, safe_stop_errors=[], boot_id='same')
    return result, dict(boot_id='same'), dict(status='PASS', audio_control=0, boot_id='same')


def test_complete_counter_evidence_still_requires_separate_human_gate():
    result, pre, post = completed()
    assert all(runner.evaluate(result, 300, pre, post).values())
    assert 'human_listening' not in runner.evaluate(result, 300, pre, post)


@pytest.mark.parametrize('field,value', [('underflows', 1), ('iq_overflow', True),
                                        ('pcm_full', True), ('playing', False)])
def test_one_discontinuity_invalidates_continuous_audio(field, value):
    result, pre, post = completed()
    result['samples'][123]['audio'][field] = value
    assert not runner.evaluate(result, 300, pre, post)['fifo_clean']


def test_no_samples_or_short_run_cannot_be_accepted():
    result, pre, post = completed()
    result['samples'] = []
    result['elapsed_total_s'] = 299.9
    checks = runner.evaluate(result, 300, pre, post)
    assert not checks['sample_count'] and not checks['fifo_clean']
    assert not checks['duration'] and not checks['display']


def test_changed_boot_or_unreleased_output_cannot_pass():
    result, pre, post = completed()
    post.update(boot_id='changed', audio_control=2)
    checks = runner.evaluate(result, 300, pre, post)
    assert not checks['same_boot'] and not checks['source_stopped']


def test_stalled_audio_counter_cannot_pass_even_with_playing_flag():
    result, pre, post = completed()
    result['samples'][100]['audio_frame_rate_hz'] = 0
    assert not runner.evaluate(result, 300, pre, post)['clock_counts']


def test_error_after_last_periodic_sample_cannot_pass():
    result, pre, post = completed()
    result['audio_before_stop']['underflows'] = 1
    assert not runner.evaluate(result, 300, pre, post)['final_interval_clean']


def test_missing_final_snapshot_cannot_pass():
    result, pre, post = completed()
    del result['audio_before_stop']
    assert not runner.evaluate(result, 300, pre, post)['final_interval_clean']


@pytest.mark.parametrize('temperature', [None, float('nan'), 86])
def test_unsafe_or_missing_temperature_cannot_pass(temperature):
    result, pre, post = completed()
    result['samples'][100]['temperature_c'] = temperature
    assert not runner.evaluate(result, 300, pre, post)['temperature']


@pytest.mark.parametrize('status,image,pre', [
    ('FAIL', 'sentinel_y3', 'hash'), ('PASS', 'sentinel_v1d', 'hash'),
    ('PASS', 'sentinel_y3', 'changed')])
def test_wrong_image_rejected_before_upload(monkeypatch, tmp_path, status, image, pre):
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    monkeypatch.setattr(runner, 'verify', lambda attempt: (tmp_path/'frozen', {}))
    monkeypatch.setattr(runner, 'sha', lambda path: 'hash')
    monkeypatch.setattr(runner, 'verified', lambda path: dict(
        status=status, image=image, prebuild_manifest_sha256=pre))
    with pytest.raises(ValueError, match='audited Y3'):
        runner.payload_files(1)


def test_v2_input_manifest_detects_modified_or_missing_rtl(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    rtl = tmp_path/'core.v'
    rtl.write_text('module core; endmodule')
    receipt = {'build_input_sha256': {'core.v': runner.sha(rtl)}}
    runner.verify_v2_inputs(receipt)
    rtl.write_text('module changed; endmodule')
    with pytest.raises(ValueError, match='changed after implementation'):
        runner.verify_v2_inputs(receipt)
    rtl.unlink()
    with pytest.raises(ValueError, match='changed after implementation'):
        runner.verify_v2_inputs(receipt)


@pytest.mark.parametrize('inputs', [None, {}, [], {'core.v': True},
                                   {'core.v': 'bad'}, {'': '0'*64}])
def test_v2_malformed_input_manifest_rejected(monkeypatch, tmp_path, inputs):
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='manifest'):
        runner.verify_v2_inputs({'build_input_sha256': inputs})


def test_v2_manifest_cannot_escape_repository(monkeypatch, tmp_path):
    root = tmp_path/'repo'
    root.mkdir()
    other = tmp_path/'outside.v'
    other.write_text('module outside; endmodule')
    monkeypatch.setattr(runner, 'ROOT', root)
    for name in ('../outside.v', str(other)):
        with pytest.raises(ValueError):
            runner.verify_v2_inputs({'build_input_sha256': {name: runner.sha(other)}})


def test_quality_capture_uses_real_observation_gaps_and_audible_coverage():
    result, pre, post = completed()
    result.update(stereo_quality_gate=True, audible_seconds=29, elapsed_total_s=30.1)
    result['samples'] = result['samples'][:25]
    for i, sample in enumerate(result['samples']):
        sample['elapsed_s'] = (i+1)*1.18
    assert all(runner.evaluate(result, 30, pre, post).values())
    result['audible_seconds'] = 0
    assert not runner.evaluate(result, 30, pre, post)['audible_coverage']
    result['samples'][10]['elapsed_s'] += 3
    assert not runner.evaluate(result, 30, pre, post)['telemetry_coverage']

