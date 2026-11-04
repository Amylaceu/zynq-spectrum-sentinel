"""X5 capture ownership, wire contract, target scheduling and UI publication."""
from types import SimpleNamespace

import numpy as np
import pytest

from src.ps.sentinel.capture_x5 import (
    ChannelCapture, MAGIC, PACKET_BYTES, SAMPLES, decode_packet, select_channel)
from src.ps.sentinel.dma import _ABORTED_BUFFERS
from src.ps.sentinel.lcd_x5 import BANK_WORDS, VERSION, X5LCD, pack_ui, displayed_label
from src.ps.sentinel.drivers.regs import lcd_ctrl as L
from src.ps.sentinel.tracker_x5 import TargetTracker


@pytest.mark.parametrize('confidence,label', [(0, '?'), (.499, '?'), (.5, 'FM'), (1, 'FM')])
def test_low_score_is_undecided_on_screen(confidence, label):
    assert displayed_label(SimpleNamespace(label='FM', confidence=confidence)) == label


class Registers:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.events = []

    def read(self, offset):
        return self.values.get(offset, 0)

    def write(self, offset, value):
        self.values[offset] = value
        self.events.append((offset, value))


def packet(selection, source=12):
    words = np.zeros(8+SAMPLES, dtype=np.uint32)
    words[:8] = [MAGIC, 17, 2, selection.channel, selection.fcw, 1, SAMPLES, source]
    words[8] = 0x80007fff
    return words


def test_selection_negative_and_nyquist_edges():
    sel = select_channel(-600000)
    assert sel.channel == 14 and sel.residual_hz == -120000
    assert sel.fcw == 0xc0000000
    assert select_channel(1919999).channel == 8
    assert select_channel(-1920000).channel == 8
    for value in (1920000, float('nan'), float('inf')):
        with pytest.raises(ValueError):
            select_channel(value)
    with pytest.raises(ValueError):
        select_channel(0, 30720000)


def test_packet_signed_iq_timestamp_and_mutation_rejected():
    sel = select_channel(-600000)
    words = packet(sel)
    decoded = decode_packet(words, sel, 12)
    assert decoded['timestamp_cycles'] == (2 << 32)+17
    assert decoded['iq'][0] == 32767/32768-1j
    words[8] = 0
    assert decoded['raw_words'][8] == 0x80007fff
    for index in (0, 3, 4, 5, 6, 7):
        damaged = packet(sel)
        damaged[index] ^= np.uint32(1)
        with pytest.raises(ValueError):
            decode_packet(damaged, sel, 12)
    with pytest.raises(ValueError):
        decode_packet(words[:-1], sel, 12)


class Buffer(np.ndarray):
    def __new__(cls, n):
        buf = np.zeros(n, dtype=np.uint8).view(cls)
        buf.freed = False
        return buf

    def invalidate(self):
        pass

    def freebuffer(self):
        self.freed = True


def fake_capture(fault=None):
    control, meta, status = Registers(), Registers(), Registers()
    dma_regs = Registers({0x34: 0x1002, 0x58: PACKET_BYTES})
    buffers, events = [], []
    def allocate(n):
        buf = Buffer(n)
        buffers.append(buf)
        return buf
    channel = SimpleNamespace(idle=True)
    def transfer(buf):
        events.append('receive_primed')
        if fault == 'transfer':
            raise IOError('transfer rejected')
    channel.transfer = transfer
    original_write = control.write
    def arm(offset, value):
        original_write(offset, value)
        if offset == 0 and value & 1:
            assert events == ['receive_primed']
            events.append('arm')
            buffers[-1].view(np.uint32)[:] = packet(select_channel(0))
            status.values[0] = (SAMPLES << 16) | 2
            if fault == 'short':
                dma_regs.values[0x58] -= 4
            if fault == 'error':
                dma_regs.values[0x34] |= 0x10
            if fault == 'timeout':
                channel.idle = False
    control.write = arm
    cap = ChannelCapture(control, meta, status,
                         SimpleNamespace(mmio=dma_regs, recvchannel=channel),
                         health=lambda: 0, allocator=allocate)
    return cap, buffers, events


def test_dma_primed_before_arm_and_freed_after_complete():
    capture, buffers, events = fake_capture()
    result = capture.acquire(select_channel(0), source=12)
    assert result['iq'].shape == (4096,)
    assert events == ['receive_primed', 'arm']
    assert buffers[0].freed and capture.engine.inflight == []


@pytest.mark.parametrize('fault', ['transfer', 'short', 'error', 'timeout'])
def test_failed_dma_quarantines_buffer_and_prevents_rearming(fault):
    capture, buffers, _ = fake_capture(fault)
    try:
        with pytest.raises((IOError, RuntimeError, TimeoutError)):
            capture.acquire(select_channel(0), source=12, timeout_s=.001)
        assert capture.failed and not buffers[0].freed
        assert any(buf is buffers[0] for buf in _ABORTED_BUFFERS)
        with pytest.raises(RuntimeError, match='reset'):
            capture.acquire(select_channel(0))
    finally:
        # Test allocations are ordinary NumPy arrays, never DMA-owned CMA.
        _ABORTED_BUFFERS[:] = [buf for buf in _ABORTED_BUFFERS if not any(buf is b for b in buffers)]


def target(bin_index, power=100):
    return SimpleNamespace(start=bin_index, stop=bin_index+8, peak_power=power)


def test_new_target_priority_five_votes_ties_and_expiry():
    tracker = TargetTracker()
    tracker.update([target(800)], 98000000, 3840000, 1)
    first = tracker.next(1)
    tracker.mark_attempt(first.key, 1)
    tracker.update([target(800), target(1000, 5)], 98000000, 3840000, 2)
    new = tracker.next(2)
    assert new.key != first.key
    for n, label in enumerate(('FM', 'AM', 'FM', 'AM', 'FM', 'AM')):
        tracker.record(first.key, {'label': label, 'confidence': .8}, 2+n/10)
    assert len(first.votes) == 5 and first.label == 'AM'
    tracker.update([], 98000000, 3840000, 10)
    assert not tracker.tracks


def test_ui_bank_ownership_and_full_palette_layout():
    right = np.arange(400*240, dtype=np.uint32).reshape(400, 240) % 4
    status = np.full((80, 800), 3, dtype=np.uint8)
    words = pack_ui(right, status)
    assert words[0] == 0xe4e4e4e4 and words[-1] == 0xffffffff
    regs = Registers({L.VERSION: VERSION})
    memory = Registers()
    lcd = X5LCD(regs, memory)
    token = lcd.submit_ui(right, status)
    assert token == 1 and memory.events[0][0] == 4*BANK_WORDS
    assert memory.read(0) == 0
    with pytest.raises(RuntimeError, match='pending'):
        lcd.submit_ui(right, status)
    regs.values[L.UI_APPLIED] = 1
    assert lcd.submit_ui(right, status) == 2
    assert memory.read(0) == words[0]
    with pytest.raises(TimeoutError):
        lcd.wait_ui(2, timeout=.001)


def test_tracker_at_capacity_replaces_missing_target_but_preserves_matched_id():
    tracker = TargetTracker(max_tracks=2)
    tracker.update([target(200, 10), target(500, 20)], 98000000, 3840000, 1)
    preserved = tracker.visible(1)[0].key
    tracker.update([target(900, 30), target(500, 20)], 98000000, 3840000, 2)
    assert len(tracker.tracks) == 2
    assert preserved in tracker.tracks
    assert any(t.first_seen == 2 for t in tracker.tracks.values())


def test_monitor_real_capture_preserved_and_latency_waits_for_applied(tmp_path, monkeypatch):
    from src.ps.sentinel.app.monitor_x5 import classify_one, display_result
    import src.ps.sentinel.app.monitor_x5 as monitor
    import hashlib
    tracker = TargetTracker()
    tracker.update([target(800)], 98000000, 3840000, 10)
    track = tracker.next(10)
    captured = decode_packet(packet(select_channel(track.frequency_hz-98000000), 0),
                             select_channel(track.frequency_hz-98000000), 0)
    events = []
    def acquire(selection, source):
        assert source == 0
        events.append('capture')
        return captured
    def predict(iq, fs):
        assert np.array_equal(iq, captured['iq']) and fs == 480000
        events.append('inference')
        return [dict(label='FM', coarse='FM', confidence=.8, detail=None)]
    hw = SimpleNamespace(channel_capture=SimpleNamespace(acquire=acquire))
    ticks = iter([10.01, 10.02, 10.03, 10.04, 10.05])
    record, iq, symbols = classify_one(hw, SimpleNamespace(predict=predict), tracker,
                                      track, tmp_path, 0, 98000000, clock=lambda: next(ticks))
    assert events == ['capture', 'inference'] and symbols is None
    path = tmp_path/record['capture_filename']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record['capture_sha256']
    with np.load(path, allow_pickle=False) as data:
        assert np.array_equal(data['words'], captured['raw_words'])
    assert record['first_label_ms'] is None and track.display_latency_ms is None
    def submit(*args):
        events.append('published')
        assert track.display_latency_ms is None
        return 2
    def wait(token):
        assert token == 2 and track.display_latency_ms is None
        events.append('applied')
    hw.lcd = SimpleNamespace(submit_ui=submit, wait_ui=wait)
    monkeypatch.setattr(monitor, 'draw_ui', lambda *a, **kw: (None, None))
    display_result(hw, tracker, track, iq, symbols, record, 98000000, 20, 40, 45,
                   0, clock=lambda: 10.2)
    assert events[-2:] == ['published', 'applied']
    assert record['first_label_ms'] == pytest.approx(200)
    assert track.display_latency_ms == pytest.approx(200)


def test_monitor_failed_page_ack_never_claims_displayed_latency(monkeypatch):
    import src.ps.sentinel.app.monitor_x5 as monitor
    tracker = TargetTracker()
    tracker.update([target(800)], 98000000, 3840000, 1)
    track = tracker.next(1)
    record = {'first_label_ms': None}
    def fail(_):
        raise TimeoutError('swap not acknowledged')
    hw = SimpleNamespace(lcd=SimpleNamespace(submit_ui=lambda *args: 1, wait_ui=fail))
    monkeypatch.setattr(monitor, 'draw_ui', lambda *a, **kw: (None, None))
    with pytest.raises(TimeoutError):
        monitor.display_result(hw, tracker, track, None, None, record,
                               98000000, 0, 0, 45, 0, clock=lambda: 1.1)
    assert record['first_label_ms'] is None and track.display_latency_ms is None


def test_monitor_truth_is_independent_and_missing_truth_not_passed():
    from src.ps.sentinel.app.monitor_x5 import summarize
    records = [dict(frequency_hz=95800000, prediction='FM', voted_label='FM', first_label_ms=200),
               dict(frequency_hz=95450000, prediction='FM', voted_label='FM', first_label_ms=300),
               dict(frequency_hz=95810000, prediction='AM-DSB', voted_label='FM', first_label_ms=None)]
    missing = summarize(records, [], 25000)
    assert missing['fm_raw_fraction'] is None and missing['fm_truth_captures'] == 0
    measured = summarize(records, [95800000], 25000)
    assert measured['fm_truth_captures'] == 2 and measured['fm_raw_fraction'] == .5
    assert measured['fm_voted_fraction'] == 1 and measured['first_observed_to_applied_median_ms'] == 250
