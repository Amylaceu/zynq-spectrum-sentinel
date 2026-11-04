"""Qt fake-board integration and exact replay state, no RF activity."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'tools/host'),str(ROOT/'src/ps')]
from PySide6 import QtWidgets,QtGui
from fake_board import FakeBoard
from sentinel_host.gui import Window
from sentinel_host.session import Recorder,Replay
from sentinel_host.model import Model


def test_fake_board_qt_record_replay_and_selection(tmp_path):
    app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    if Path('C:/Windows/Fonts/segoeui.ttf').is_file():
        QtGui.QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
        app.setFont(QtGui.QFont('Segoe UI',10))
    with FakeBoard() as board:
        window=Window()
        window.show()
        window.start_worker(address='127.0.0.1',port=board.service.tcp_port)
        path=tmp_path/'fake.zsr'
        window.recorder=Recorder(path,source='synthetic-test')
        end=time.monotonic()+2
        while time.monotonic()<end:
            app.processEvents()
            time.sleep(.005)
        assert window.model.spectrum_count >= 10
        assert window.painted_frames >= 10
        assert len(window.model.targets)==1
        assert len(window.model.iq)==512
        window.select_target(0,0)
        app.processEvents()
        window.stop_worker()
        window.recorder.close();window.recorder=None
        replay=Model()
        for elapsed,header,payload in Replay(path):
            replay.apply(header,payload,observed=elapsed)
        assert replay.targets==window.model.targets
        assert list(replay.events)==list(window.model.events)
        assert replay.histogram==window.model.histogram
        assert not window.data_errors
        assert window.grab().save(str(tmp_path/'gui.png'))
        window.close()
