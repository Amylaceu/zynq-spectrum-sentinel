"""Render a complete UI from explicitly synthetic fake-board telemetry."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/host'),str(ROOT/'src/ps'),str(ROOT)]
from PySide6 import QtWidgets,QtCore,QtGui
from fake_board import FakeBoard
from sentinel_host.gui import Window


def main():
    app=QtWidgets.QApplication([])
    if Path('C:/Windows/Fonts/segoeui.ttf').is_file():
        QtGui.QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    app.setFont(QtGui.QFont('Segoe UI',10));app.setStyle('Fusion')
    with FakeBoard() as fake:
        w=Window();w.show()
        w.start_worker(address='127.0.0.1',port=fake.service.tcp_port)
        def finish():
            w.title.setText('OFFLINE / SYNTHETIC TEST — not a board measurement')
            w.grab().save(str(ROOT/'report/figures/host_fake_preview.png'))
            w.close()
        QtCore.QTimer.singleShot(5000,finish)
        app.exec()


if __name__=='__main__':
    main()
