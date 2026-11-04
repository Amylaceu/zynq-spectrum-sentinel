"""Association failures must be rejected before an RF diagnosis is trusted."""
import pytest

from src.ps.sentinel.app.diagnose_x1 import check_pair, check_rf_readback, finite_capture


def test_preserves_observed_two_hz_lo_rounding():
    assert check_rf_readback(96399998, 3840000) == {
        'actual_lo_hz': 96399998, 'actual_rate_hz': 3840000}


@pytest.mark.parametrize('lo,rate', [(96399994, 3840000), (96400006, 3840000),
                                  (96400000, 3839999), (95800000, 3840000)])
def test_rejects_incorrect_rf_readback(lo, rate):
    with pytest.raises(RuntimeError, match='LO='):
        check_rf_readback(lo, rate)


@pytest.mark.parametrize('before', [0, 64, 0xffffffff])
def test_accepts_exactly_one_frame_including_counter_wrap(before):
    after = (before + 1) & 0xffffffff
    check_pair(before, after, 1, 2048, after, (2048, 1, 1))


@pytest.mark.parametrize('after,samples,spec,delta', [
    (64, 2048, 65, (2048, 1, 1)),
    (66, 2048, 65, (2048, 1, 1)),
    (65, 2047, 65, (2048, 1, 1)),
    (65, 2048, 64, (2048, 1, 1)),
    (65, 2048, 65, (4096, 2, 1)),
    (65, 2048, 65, (2048, 1, 0)),
])
def test_rejects_stale_extra_partial_and_unpaired_frames(after, samples, spec, delta):
    with pytest.raises(RuntimeError, match='association failed'):
        check_pair(64, after, 1, samples, spec, delta)


def test_refuses_capture_of_multiple_frames_before_accessing_hardware():
    with pytest.raises(ValueError, match='sole frame'):
        finite_capture(None, 'test', frames=2)
