from types import SimpleNamespace

import numpy as np
import pytest

from src.ps.sentinel.ui_v3 import draw_ui_v3
from src.ps.sentinel.ui_v3.theme import modulation_style
from src.ps.sentinel.lcd_x5 import pack_ui
from src.ps.sentinel.tracker_x5 import Track


@pytest.mark.parametrize('view', ['SIG', 'TGT', 'STAT'])
@pytest.mark.parametrize('tx', [False, True])
def test_pages_stay_inside_frozen_banks_and_palette(view, tx):
    track = Track(1, 95800000, 200000, 1234, 99, 100)
    track.label, track.confidence = 'QPSK', .91
    right, status = draw_ui_v3([track], selected=1, iq=np.array([np.nan, np.inf, 1+1j]),
        view=view, now=100, tx_active=tx, tx_atten_db=40 if tx else None)
    assert right.shape == (400, 240) and status.shape == (80, 800)
    assert set(np.unique(right)) <= {0, 1, 2, 3}
    assert set(np.unique(status)) <= {0, 1, 2, 3}
    assert pack_ui(right, status).shape == (10000,)


def test_tx_flash_keeps_text_and_does_not_change_off_state():
    first = draw_ui_v3([], now=100, view='SIG', tx_active=True, tx_atten_db=52)[1]
    second = draw_ui_v3([], now=100.5, view='SIG', tx_active=True, tx_atten_db=52)[1]
    assert np.any(first[3:29, 532:693] != second[3:29, 532:693])
    assert np.any(second[3:29, 532:693] == 2), 'TX ON text/border persists in dim phase'
    assert np.array_equal(draw_ui_v3([], now=100, view='SIG')[1],
                          draw_ui_v3([], now=100.5, view='SIG')[1])


@pytest.mark.parametrize('attenuation', [None, 39, 90, float('nan')])
def test_unsafe_tx_display_is_rejected(attenuation):
    with pytest.raises(ValueError):
        draw_ui_v3([], tx_active=True, tx_atten_db=attenuation)


def test_unknown_score_and_families_use_text_as_well_as_color():
    assert modulation_style('FM') == (1, 'A')
    assert modulation_style('OOK') == (2, 'D')
    assert modulation_style('QPSK') == (3, 'D')
    assert modulation_style('?')[1] == '?'


def test_empty_target_and_unavailable_selftest_are_renderable():
    for checks in (None, [('AD9361 ID', True), ('TEMP', None), ('BITSTREAM', False)]):
        right, status = draw_ui_v3([], view='TGT', selftest_checks=checks)
        assert right.any() and status.any()
    with pytest.raises(ValueError, match='page'):
        draw_ui_v3([], view='INVALID')


def test_bitmap_text_does_not_require_modern_board_pillow_apis():
    from src.ps.sentinel.ui_v3.widgets import text
    class LegacyPen:
        def bitmap(self, xy, mask, fill):
            self.mask = mask
    pen = LegacyPen()
    label = text(pen, (0, 0), 'ABCDEFG', 35)
    assert 0 < len(label) < 7
    assert pen.mask.mode == '1' and pen.mask.getbbox() is not None
