"""Render four deterministic fake-board pages without any hardware access."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tools/host'), str(ROOT/'src/ps'), str(ROOT)]

from PySide6 import QtCore, QtGui, QtWidgets
from fake_board import preview_packets
from sentinel_host.shell import Window
from sentinel_host.theme import configure


def render(output):
    output.mkdir(parents=True, exist_ok=True)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    for directory in QtCore.QStandardPaths.standardLocations(QtCore.QStandardPaths.FontsLocation):
        for name in ('msyh.ttc', 'msyhbd.ttc', 'segoeui.ttf', 'consola.ttf'):
            font = Path(directory)/name
            if font.is_file():
                QtGui.QFontDatabase.addApplicationFont(str(font))
    configure(app)
    window = Window()
    window.timer.stop()
    window.resize(1920, 1080)
    window.show()
    for header, payload in preview_packets():
        window.packet(header, payload, time.monotonic())
    app.processEvents()
    records = []
    for page, name in enumerate(('monitor', 'recognition', 'audio', 'loopback')):
        window.select_page(page)
        window._last_curves = window._last_tables = -1.
        window.refresh()
        app.processEvents()
        path = output/(name+'.png')
        window.grab().save(str(path))
        rect = window.twin_canvas.viewport()
        records.append(dict(page=name, path=path.name,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            lcd_width_px=rect.width(), lcd_height_px=rect.height()))
    window.toggle_focus()
    app.processEvents()
    focus_width = window.twin_canvas.viewport().width()
    errors = list(window.data_errors)
    window.close()
    result = dict(schema='g4plus_preview/1',source='OFFLINE_SYNTHETIC_NOT_BOARD_MEASUREMENT',
                  viewport=[1920,1080],screenshots=records,focused_lcd_width_px=focus_width,
                  data_errors=errors,hardware_connected=False)
    path=output/'preview.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    Path(str(path)+'.sha256').write_text(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name+'\n')
    print(json.dumps(result,ensure_ascii=False))
    return result


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'report/figures/host_v2')
    render(p.parse_args().output)
