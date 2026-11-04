"""Workbench geometry, scaled hit routing and truthful offline presentation."""
import hashlib
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT/'tools/host'), str(ROOT/'src/ps')]
import numpy as np
import pytest
from PySide6 import QtCore, QtWidgets
from PySide6.QtTest import QTest
from sentinel.ui_v3.layout import hit_map, resolve_hit
from sentinel_host.shell import Window, AdaptiveCanvas, demo_page
from sentinel_host.theme import configure
from fake_board import preview_packets, FakeBoard


@pytest.fixture
def app():
    value = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    configure(value)
    return value


@pytest.fixture
def window(app):
    value = Window()
    value.timer.stop()
    value.show()
    app.processEvents()
    try:
        yield value
    finally:
        value.close()
        app.processEvents()


def fixture_data(window):
    for header, payload in preview_packets():
        window.packet(header, payload, time.monotonic())
    window.refresh()


@pytest.mark.parametrize('scale', [1., 1.25, 2.])
def test_twenty_physical_control_clicks_at_each_scale(app, scale):
    canvas = AdaptiveCanvas()
    canvas.resize(round(800*scale), round(480*scale))
    canvas.show()
    app.processEvents()
    controls = hit_map([SimpleNamespace(key=7)], view='SIG')
    received = []
    canvas.click.connect(lambda x, y: received.append((x, y)))
    try:
        for index in range(20):
            hit = controls[index % len(controls)]
            left, top, right, bottom = hit['rect']
            # Include positions near edges, as well as the centres.
            x = left+2 if index % 2 else (left+right)//2
            y = top+2 if index % 2 else (top+bottom)//2
            rect = canvas.viewport()
            position = QtCore.QPoint(round(rect.x()+(x+.5)*rect.width()/800),
                                    round(rect.y()+(y+.5)*rect.height()/480))
            QTest.mouseClick(canvas, QtCore.Qt.MouseButton.LeftButton, pos=position)
            assert resolve_hit(*received[-1], [SimpleNamespace(key=7)])['action'] == hit['action']
        assert len(received) == 20
        assert canvas.physical(QtCore.QPointF(-1, -1)) is None
    finally:
        canvas.close()


def test_1080p_adaptive_and_focus_dimensions_without_replacing_twin(app, window):
    fixture_data(window)
    canvas = window.twin_canvas
    assert canvas.viewport().width() >= 1000
    for index in range(7):
        window.select_page(index)
        app.processEvents()
        assert window.twin_canvas is canvas
        expected = window.panorama_panel if index == 4 else window.workbench
        assert window.center_stack.currentWidget() is expected
    window.toggle_focus()
    app.processEvents()
    assert canvas.viewport().width() >= 1600
    assert canvas.viewport().height() == 960
    window.toggle_focus()
    assert not window.focused
    assert not window.data_errors


def test_demo_routing_and_manual_thirty_second_override(window):
    expected = [('A',1,0),('A',2,1),('A',3,2),('B',5,3),('B',6,3),('B',8,5)]
    for group, segment, page in expected:
        window.packet(dict(type='demo',group=group,segment=segment), b'', time.monotonic())
        assert window.active_page == page
    window.select_page(4, manual=True)
    assert window.manual_until > time.monotonic()+29
    window.packet(dict(type='demo',group='A',segment=3), b'', time.monotonic())
    assert window.active_page == 4
    window.manual_until = 0
    window.packet(dict(type='demo',group='A',segment=2), b'', time.monotonic())
    assert window.active_page == 1


def test_source_labels_missing_data_and_bounded_history(window):
    fixture_data(window)
    assert window.model.audio['source'] == 'ps_parallel_demod'
    assert '独立解调' in window.panel_groups[2][1][0].source.text()
    assert '离线合成' in window.mode_badge.text()
    assert '未校准' in window.panel_groups[0][1][0].findChildren(QtWidgets.QLabel)[1].text()
    assert '非正式评测' in window.panel_groups[3][1][0].findChildren(QtWidgets.QLabel)[1].text()
    assert '尚未载入实测结果' in window.panel_groups[4][1][0].state.text()
    window.select_page(2)
    audio = window.panel_groups[2][1][0]
    assert all(not b.isEnabled() for b in audio.findChildren(QtWidgets.QPushButton))
    for i in range(300):
        window.model.apply(dict(type='amc',track=1,prediction='FM',score=.8))
    assert len(window.model.amc_history) == 256


def test_same_fixture_raster_is_deterministic(app, window):
    fixture_data(window)
    window.select_page(1)
    app.processEvents()
    def pixels():
        image = window.grab().toImage()
        return bytes(image.constBits())
    first = pixels()
    # A repaint without input must not advance a waterfall or regenerate data.
    window.refresh()
    app.processEvents()
    assert pixels() == first


def test_new_shell_fake_socket_click_roundtrip(app, window):
    with FakeBoard() as board:
        window.start_worker(address='127.0.0.1', port=board.service.tcp_port)
        def pump():
            end=time.monotonic()+.6
            while time.monotonic() < end:
                app.processEvents()
                time.sleep(.005)
        pump()
        window.twin_click(665,12)
        pump()
        assert window.twin.ui_state['view'] == 'TGT'
        assert board.ui_state.view == 'TGT'
        assert not window.data_errors
        window.stop_worker()


def test_frozen_build_report_uses_bundled_verified_evidence(tmp_path,monkeypatch):
    import shutil
    monkeypatch.setattr(sys,'_MEIPASS',str(tmp_path),raising=False)
    bundle=tmp_path/'build_evidence'
    bundle.mkdir()
    source=ROOT/'board/overlay/sentinel_v2_100m'
    for name in ('acceptance.json','acceptance.json.sha256'):
        shutil.copyfile(source/name,bundle/name)
    assert Window.load_build_info()['image']=='sentinel_v2_100m'
    with (bundle/'acceptance.json').open('ab') as stream:
        stream.write(b' ')
    assert Window.load_build_info()=={}
