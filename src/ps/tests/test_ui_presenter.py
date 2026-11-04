"""Check bank ownership, acknowledgement and scheduler behaviour without RF."""
import numpy as np
import pytest

from src.ps.sentinel.ui_v3.presenter import Presenter
from src.ps.sentinel.tracker_x5 import Track


class Clock:
    value = 100.0
    def __call__(self):
        return self.value


class LCD:
    def __init__(self, clock):
        self.clock, self.banks, self.waited = clock, [], []
    def submit_ui(self, right, status):
        self.banks.append((right.copy(), status.copy()))
        self.clock.value += .003
        return len(self.banks)
    def wait_ui(self, token):
        self.waited.append(token)
        self.clock.value += .01


def test_cadences_coalesce_and_unchanged_banks_are_skipped():
    clock = Clock()
    lcd = LCD(clock)
    ui = Presenter(lcd, clock=clock)
    assert ui.present([], view='SIG', frame=1) == 1
    clock.value = 100.1
    assert ui.present([], frame=2) is None
    clock.value = 100.22
    assert ui.present([], frame=3) is None, 'status not yet due; identical right bank'
    clock.value = 100.51
    assert ui.present([], frame=4) == 2
    assert lcd.waited == [1, 2]
    assert ui.summary()['errors'] == 0
    assert ui.summary()['median_ms'] == pytest.approx(3)
    assert ui.summary()['acknowledgement_p95_ms'] == pytest.approx(10)


def test_right_changes_do_not_accelerate_status_updates():
    clock = Clock()
    lcd = LCD(clock)
    ui = Presenter(lcd, clock=clock)
    track = Track(1, 95800000, 200000, 123, 99, 100)
    ui.present([track], view='SIG', frame=1)
    clock.value = 100.21
    track.label, track.confidence = 'FM', .9
    ui.present([track], frame=99)
    assert not np.array_equal(lcd.banks[0][0], lcd.banks[1][0])
    assert np.array_equal(lcd.banks[0][1], lcd.banks[1][1])


def test_submit_errors_propagate_and_do_not_claim_success():
    clock = Clock()
    lcd = LCD(clock)
    ui = Presenter(lcd, clock=clock)
    def fail(token):
        raise TimeoutError('injected hardware acknowledgement failure')
    lcd.wait_ui = fail
    with pytest.raises(TimeoutError):
        ui.present([])
    assert ui.summary()['errors'] == 1
    assert ui.summary()['submissions'] == 0


def test_v2_fallback_filters_v3_arguments_and_preserves_contract():
    clock = Clock()
    lcd = LCD(clock)
    ui = Presenter(lcd, version='v2', clock=clock)
    ui.present([], view='TGT', selftest_checks=[('TEMP', True)], sent_label='QPSK')
    assert [a.shape for a in lcd.banks[0]] == [(400, 240), (80, 800)]
    assert ui.summary()['version'] == 'v2'


def test_unsafe_transmit_indication_is_rejected_before_bank_write():
    clock = Clock()
    lcd = LCD(clock)
    ui = Presenter(lcd, clock=clock)
    with pytest.raises(ValueError, match='attenuation'):
        ui.present([], tx_active=True, tx_atten_db=39)
    assert not lcd.banks
