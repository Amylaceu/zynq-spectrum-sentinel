"""Reject plausible but misleading X5 UI/latency/continuity evidence."""
from pathlib import Path
import sys

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from analyze_x5_board import check_votes, metrics, decode_processing_status


def record(label='FM', score=.9, voted='FM', displayed='FM'):
    return dict(track=1, score=score, prediction=label, votes=[[label, score]],
                voted_label=voted, voted_score=score, displayed_label=displayed,
                ui_applied_monotonic_s=1.75, first_seen_monotonic_s=1,
                first_label_ms=750, frequency_hz=95800000)


def result():
    records = []
    for index in range(5):
        item = record()
        item.update(votes=[['FM', .9]]*(index+1),
                    ui_applied_monotonic_s=1.75+index,
                    first_label_ms=750 if index == 0 else None)
        records.append(item)
    return dict(records=records, status='completed', stopped_by_signal=False,
                telemetry=[dict(temperature_c=50, rx_rssi_dbm=-55,
                                tx_atten_mdb=[89750, 89750], processing_status=0,
                                display_fps=49)], fm_truth_hz=[95800000],
                requested_lo_hz=96400000, elapsed_total_s=120.1,
                duration_requested_s=120)


def test_separate_formal_frequency_and_latency_requirements():
    value = metrics(result())
    assert value['automated_y2_status'] == 'PASS_AUTOMATED_AWAITING_VISUAL'
    assert value['original_x5_checks']['observed_latency_under_500ms'] is False
    assert value['original_x5_checks']['formal_98mhz_truth_fm_80pct'] is None


@pytest.mark.parametrize('field,value', [('votes', [['BPSK', .9]]),
                                       ('voted_label', 'BPSK'),
                                       ('displayed_label', '?'),
                                       ('first_label_ms', 1)])
def test_forged_vote_or_latency_rejected(field, value):
    item = record()
    item[field] = value
    with pytest.raises(ValueError):
        check_votes([item])


def test_low_scores_stay_unknown_despite_an_fm_vote():
    assert check_votes([record(score=.4, displayed='?')]) == 1
    with pytest.raises(ValueError):
        check_votes([record(score=.4)])


def test_missing_truth_cannot_pass_using_model_predictions():
    data = result()
    data['fm_truth_hz'] = []
    assert metrics(data)['automated_y2_status'] == 'NOT_EVALUATED'


def test_warmup_alone_cannot_establish_full_five_vote_accuracy():
    data = result()
    data['records'] = data['records'][:4]
    values = metrics(data)
    assert values['fm_displayed_fraction'] == 1
    assert values['fm_full_five_vote_captures'] == 0
    assert values['automated_y2_status'] == 'NOT_EVALUATED'


def test_track_timestamp_cannot_be_reset_to_hide_latency():
    records = result()['records']
    records[1]['first_seen_monotonic_s'] += .1
    with pytest.raises(ValueError, match='first-seen'):
        check_votes(records)


def test_ui_evidence_must_have_monotonic_chronology():
    records = result()['records']
    records[-1]['ui_applied_monotonic_s'] = 1.8
    with pytest.raises(ValueError, match='chronology'):
        check_votes(records)


@pytest.mark.parametrize('field,value', [('temperature_c', None), ('temperature_c', 86),
                                       ('rx_rssi_dbm', -29), ('processing_status', 1),
                                       ('tx_atten_mdb', [30000, 89750])])
def test_safety_or_sample_loss_rejected(field, value):
    data = result()
    data['telemetry'][0][field] = value
    with pytest.raises(ValueError):
        metrics(data)


def test_short_or_interrupted_trial_fails():
    data = result()
    data['stopped_by_signal'] = True
    assert metrics(data)['automated_y2_status'] == 'FAIL'


@pytest.mark.parametrize('value', [0, 4, 8, 16, 28])
def test_latency_handshake_bits_are_not_sample_faults(value):
    data = result()
    data['telemetry'][0]['processing_status'] = value
    assert metrics(data)['automated_y2_status'] == 'PASS_AUTOMATED_AWAITING_VISUAL'
    assert decode_processing_status(value)['latency_valid'] == bool(value & 4)


@pytest.mark.parametrize('value', [1, 2, 5, 6, 32, -1, None, 4.0, True])
def test_faults_reserved_or_malformed_status_rejected(value):
    data = result()
    data['telemetry'][0]['processing_status'] = value
    with pytest.raises(ValueError):
        metrics(data)
