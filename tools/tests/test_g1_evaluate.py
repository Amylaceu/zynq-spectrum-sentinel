"""Evidence acceptance must fail closed without contacting a development board."""
import copy
import hashlib
import json

import pytest

from tools.g1_evaluate import evaluate


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')
    path.with_name(path.name+'.sha256').write_text(
        hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name)


@pytest.fixture
def measurement(tmp_path):
    zero = dict(status='PASS', gpio_data=0, source_ctrl=0, audio_control=0)
    demo = dict(group='A', status='PASS', completed_cycles=3, segments=[],
                cycles_timing=[dict(wall_seconds=103) for _ in range(3)],
                final_stop_readback=zero, runtime=dict(segments=[]))
    start = 100.0
    for i in range(12):
        number = i % 4+1
        seconds = (10, 40, 30, 15)[number-1]
        result = dict(status='completed' if number == 3 else 'PASS')
        if number == 3:
            result.update(audible_seconds=29, audio_before_stop=dict(underflows=0))
        path = tmp_path/str(i)/'result.json'
        save(path, result)
        demo['segments'].append(dict(number=number, duration_requested_s=seconds,
            evidence_dir=str(i), result_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            exit_code=0, stop_readback=copy.deepcopy(zero)))
        demo['runtime']['segments'].append(dict(source='rf' if number != 4 else 'test',
            tx_attenuation_before_reset_db=[89.75, 89.75],
            started_monotonic_s=start-1, content_started_monotonic_s=start))
        start += seconds+2
    save(tmp_path/'demo.json', demo)
    return tmp_path, demo


def test_complete_functionality_does_not_fabricate_wav(measurement):
    path, _ = measurement
    result = evaluate(path)
    assert result['functional_status'] == 'PASS'
    assert result['status'] == 'FAIL'
    assert result['metrics']['transition_seconds'] == [2]*11
    assert result['metrics']['transition_target_pass']
    assert not result['metrics']['wav_target_pass']


def test_cold_cycle_and_unsafe_final_state_cannot_be_ignored(measurement):
    path, demo = measurement
    demo['cycles_timing'][0]['wall_seconds'] = 117
    demo['final_stop_readback']['audio_control'] = 1
    save(path/'demo.json', demo)
    result = evaluate(path)
    assert not result['metrics']['each_cycle_le_110s']
    assert result['functional_status'] == 'FAIL'


@pytest.mark.parametrize('broken', ['digest', 'reference', 'escape'])
def test_corrupt_or_unrelated_evidence_is_rejected(measurement, broken):
    path, demo = measurement
    if broken == 'digest':
        (path/'0/result.json').write_text('{}')
    elif broken == 'reference':
        demo['segments'][0]['result_sha256'] = '0'*64
        save(path/'demo.json', demo)
    else:
        demo['segments'][0]['evidence_dir'] = '../outside'
        save(path/'demo.json', demo)
    with pytest.raises(ValueError):
        evaluate(path)


def test_missing_timing_is_unmeasured_not_zero(measurement):
    path, demo = measurement
    del demo['runtime']['segments'][2]['content_started_monotonic_s']
    save(path/'demo.json', demo)
    result = evaluate(path)
    assert result['metrics']['transition_median_seconds'] is None
    assert not result['metrics']['transition_target_pass']
