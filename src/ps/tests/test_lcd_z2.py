from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from src.ps.sentinel.lcd_z2 import pack_ui, draw_ui, PALETTE_RGB565, CLASS_COLOR, Z2LCD, VERSION
from src.ps.sentinel.ui_events import EventLog
from src.ps.sentinel.drivers.regs import lcd_ctrl as R


def track(key=1, label='FM', confidence=.9):
    return SimpleNamespace(key=key, label=label, confidence=confidence,
        frequency_hz=95800000, bandwidth_hz=180000, power=123, display_latency_ms=481)


def test_all_colors_roundtrip_both_banks_without_padding_spill():
    values = (np.arange(160000, dtype=np.uint32) % 8).astype(np.uint8)
    packed = pack_ui(values[:96000].reshape(400, 240), values[96000:].reshape(80, 800))
    decoded = np.column_stack([(packed >> (3*lane)) & 7 for lane in range(10)]).reshape(-1)
    assert np.array_equal(decoded, values)
    assert packed.nbytes == 64000 < 65536
    assert not np.any(packed >> 30)
    assert len(set(PALETTE_RGB565)) == 8
    assert len({CLASS_COLOR[c] for c in ('FM', 'PSK', 'QAM', 'FSK', 'OOK')}) == 5


def test_version5_cannot_receive_version6_pixels():
    registers = SimpleNamespace(read=lambda _: 0x4c430005)
    with pytest.raises(ValueError, match='version 6'):
        Z2LCD(registers, None)
    assert VERSION == 0x4c430006


def test_render_tx_off_green_on_red_and_five_timestamped_events():
    events = EventLog(clock=lambda: datetime(2026, 11, 3, 3, 0, 0, tzinfo=timezone.utc))
    for index in range(7):
        events.add('ALARM' if index == 6 else 'NEW', str(index))
    assert len(events.latest()) == 5
    assert events.latest()[0].timestamp_utc == '03:00:00Z'
    for enabled, color in ((False, 5), (True, 4)):
        right, status = draw_ui([track()], selected=1, tx_on=enabled, events=events.latest())
        assert color in status[40:59, :160]
        assert 4 in status[:, 406:]
        assert right.shape == (400, 240) and status.shape == (80, 800)
        assert pack_ui(right, status).shape == (16000,)


def test_only_changes_emit_events_and_low_confidence_is_unknown():
    events = EventLog()
    events.observe([track()]); events.observe([track()])
    assert len(events.events) == 1 and events.latest()[0].kind == 'NEW'
    events.observe([track(label='QPSK', confidence=.4)])
    assert events.latest()[0].kind == 'AMC' and events.latest()[0].text.endswith('FM>?')
    events.observe([track(key=i) for i in range(600)])
    assert len(events.labels) == 512 and len(events.events) == 5


def test_out_of_palette_rejected():
    with pytest.raises(ValueError):
        pack_ui(np.full((400, 240), 8), np.zeros((80, 800), dtype=np.uint8))


def test_driver_owns_only_inactive_bank_and_requires_applied_ack():
    regs = {R.VERSION: VERSION, R.UI_EPOCH: 0, R.UI_APPLIED: 0, R.STATUS: 0}
    registers = SimpleNamespace(read=lambda offset: regs[offset],
                               write=lambda offset, value: regs.__setitem__(offset, value))
    words = np.full(32768, 0xdeadbeef, dtype=np.uint32)
    memory = SimpleNamespace(array=words, read=lambda offset: int(words[offset//4]))
    lcd = Z2LCD(registers, memory)
    right, status = np.full((400, 240), 6, np.uint8), np.full((80, 800), 7, np.uint8)
    assert lcd.submit_ui(right, status) == 1
    assert np.all(words[:16384] == 0xdeadbeef)
    assert np.all(words[32384:] == 0xdeadbeef)
    assert np.array_equal(words[16384:32384], pack_ui(right, status))
    with pytest.raises(RuntimeError, match='pending'):
        lcd.submit_ui(right, status)
    before = words[16384:].copy()
    regs[R.UI_APPLIED] = 1
    assert lcd.submit_ui(right, status) == 2
    assert np.array_equal(words[16384:], before)
