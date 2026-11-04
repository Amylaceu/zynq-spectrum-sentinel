"""PS pixel contract, frozen golden raster and physical click round trip."""
import hashlib
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import zlib

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT/'src/ps'), str(ROOT/'tools/host')]
from sentinel.lcd_x5 import pack_ui, X5LCD, BANK_WORDS
from sentinel.display_twin import unpack_ui, submitted_frame, power_q88, ui_layer
from sentinel.ui_v3.state import UIState
from sentinel.ui_v3.layout import resolve_hit
from sentinel_host.twin import Twin, TwinCanvas
from sim.golden.render import render_frame


def test_ps_every_pixel_and_active_bank_full_readback():
    rng = np.random.default_rng(817)
    right = rng.integers(0, 4, (400, 240), dtype=np.uint8)
    status = rng.integers(0, 4, (80, 800), dtype=np.uint8)
    memory = np.zeros(2*BANK_WORDS, dtype=np.uint32)
    registers = {0xfc: 0x4c430005, 8: 0, 16: 0, 20: 0}
    lcd = X5LCD(SimpleNamespace(read=lambda a: registers[a], write=lambda a,v: registers.__setitem__(a,v)),
                SimpleNamespace(array=memory, read=lambda a: int(memory[a//4])))
    epoch = lcd.submit_ui(right, status)
    registers[16] = epoch
    payload, info = submitted_frame(lcd, right, status, epoch, readback=True)
    a, b = unpack_ui(payload)
    assert np.array_equal(a, right) and np.array_equal(b, status)
    assert info['readback_verified'] and info['sha256'] == info['readback_sha256']
    memory[BANK_WORDS+5023] ^= 16
    with pytest.raises(IOError, match='readback'):
        submitted_frame(lcd, right, status, epoch, readback=True)


def test_frozen_golden_raster_against_scalar_rtl_equations():
    q = np.linspace(-32768, 24000, 560).astype('<i2')
    wf = np.tile(np.arange(560, dtype=np.uint16) % 256, (240, 1))
    actual = render_frame(q, None, q, None, wf, None, None, dict(profile='x5_frozen'))
    def ordinate(raw):
        delta = 23119-int(raw)
        return 159 if raw == -32768 or delta >= 25600 else 0 if delta <= 0 else delta//160
    for x in range(560):
        current, previous = ordinate(q[x]), ordinate(q[max(0, x-1)])
        for y in (0, 31, 32, 80, 159):
            expected = 0x18c3 if y % 32 == 0 or x % 80 == 0 else 0
            if min(current,previous) <= y <= max(current,previous): expected = 0x07e0
            if y == current and x % 8 < 4: expected = 0xf800
            assert actual[y,x] == expected
        level = int(wf[0,x]); n = level & 63
        expected = [n >> 1, (n << 5) | 31, ((n >> 1) << 11) | (63 << 5) | (31-(n >> 1)),
                    (31 << 11) | ((63-n) << 5)][level >> 6]
        assert actual[160,x] == expected


def test_power_q88_matches_numeric_reference_and_reduction():
    from sim.golden.spectrum import to_db_q88
    rng = np.random.default_rng(12)
    p = rng.integers(0, 0xffffffff, 2048, dtype=np.uint32)
    p[:3] = [0, 1, 2]
    reference = to_db_q88(p)
    edges = np.arange(561)*2048//560
    expected = np.array([reference[edges[i]:edges[i+1]].max() for i in range(560)])
    assert np.array_equal(power_q88(p), expected)


def test_ui_state_hitmap_boundaries_and_timed_feedback():
    now = [1.]
    state = UIState(clock=lambda: now[0])
    assert resolve_hit(640, 0, [], 'SIG')['action'] == 'tab:TGT'
    assert resolve_hit(797, 478, [], 'SIG')['action'] == 'soft:NEXT'
    with pytest.raises(ValueError): resolve_hit(799, 479, [], 'SIG')
    assert resolve_hit(559, 399, [], 'SIG')['action'] == 'spectrum'
    with pytest.raises(ValueError): resolve_hit(800, 480, [])
    state.change('tab:TGT', [640,0,720,29], [1,10])
    assert state.snapshot()['pressed']
    now[0] += .31
    assert not state.snapshot()['pressed'] and state.snapshot()['rect']
    now[0] += .2
    assert state.snapshot()['rect'] is None


def test_twin_message_matches_golden_and_rejects_compressed_bomb():
    twin = Twin()
    right = np.zeros((400,240), dtype=np.uint8)
    status = np.full((80,800), 3, dtype=np.uint8)
    raw = pack_ui(right,status).astype('<u4').tobytes()
    payload = zlib.compress(raw)
    twin.apply(dict(type='ui_frame', epoch=7, sha256=hashlib.sha256(raw).hexdigest()), payload)
    q = np.full(560, 40*256, dtype='<i2')
    twin.apply(dict(type='pl_frame', profile='x5_frozen', lo_hz=96400000), zlib.compress(q.tobytes()))
    expected = render_frame(q,None,None,None,twin.waterfall,None,ui_layer(payload),dict(profile='x5_frozen'))
    assert np.array_equal(twin.render(), expected)
    with pytest.raises(ValueError): unpack_ui(zlib.compress(b'\0'*1000000))
    with pytest.raises(ValueError): unpack_ui(payload+b'trailing')


def test_fake_board_physical_click_updates_received_ps_epoch(tmp_path):
    from PySide6 import QtWidgets, QtCore
    from fake_board import FakeBoard
    from sentinel_host.gui import Window
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    with FakeBoard() as board:
        window = Window()
        window.show()
        window.start_worker(address='127.0.0.1', port=board.service.tcp_port)
        def pump(seconds):
            end = time.monotonic()+seconds
            while time.monotonic() < end:
                app.processEvents(); time.sleep(.005)
        try:
            pump(.7)
            assert window.views.currentIndex() == 0
            window.twin_click(665, 12)
            pump(.7)
            assert window.twin.ui_state['view'] == 'TGT'
            assert board.ui_state.view == 'TGT'
            assert window.twin.ui_count >= 4 and window.twin.pl_count >= 4
            assert window.twin_painted >= 4
            canvas = window.twin_canvas
            rect = canvas.viewport()
            assert canvas.physical(QtCore.QPointF(rect.x()+rect.width()/2, rect.y()+rect.height()/2)) == (400,240)
            assert not window.data_errors
        finally:
            window.close()
