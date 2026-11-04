"""Run the J-v5 candidate or render its live-action overview; no automatic RF start.

Example: python tools/host/product.py --preview-dir report/figures/host_j_v4
The accepted legacy executable remains unchanged until candidate acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = (Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False)
        else Path(__file__).resolve().parents[2])
sys.path[:0] = [str(ROOT/'tools/host'), str(ROOT/'src/ps'), str(ROOT)]


def app_instance():
    from PySide6 import QtCore, QtGui, QtWidgets
    from sentinel_host.theme import configure
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    for directory in QtCore.QStandardPaths.standardLocations(QtCore.QStandardPaths.FontsLocation):
        for name in ('msyh.ttc', 'msyhbd.ttc', 'consola.ttf', 'segoeui.ttf'):
            path = Path(directory)/name
            if path.is_file():
                QtGui.QFontDatabase.addApplicationFont(str(path))
    configure(app)
    return app


def preview(output):
    from PySide6 import QtCore, QtGui
    from fake_board import preview_packets
    from sentinel_host.live_catalog import PAGES, FEATURES
    from sentinel_host.product import Window
    app = app_instance()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    window = Window()
    window.timer.stop()
    window.preview_mode = True
    window.resize(1920, 1080)
    window.show()
    for header, payload in preview_packets():
        window.packet(header, payload, time.monotonic())
    app.processEvents()
    shots = []
    for index, (title, scene, page, key) in enumerate(window.live_actions):
        window.select_page(page)
        window._refresh_detail_at = 0
        window.refresh()
        app.processEvents()
        path = output/('%02d.png' % (index+1))
        if not window.grab().save(str(path)):
            raise OSError('Failed saving screenshot')
        shots.append(dict(button=index+1, page=page+1, title=title, scene=scene, file=path.name,
                          sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                          feature_keys=[key], twin_viewport_width_px=window.twin_canvas.viewport().width(),
                          twin_mode='main'))
    sheet = QtGui.QImage(960*2, 540*2, QtGui.QImage.Format.Format_RGB32)
    sheet.fill(QtGui.QColor('#0B121B'))
    painter = QtGui.QPainter(sheet)
    for i, shot in enumerate(shots):
        image = QtGui.QImage(str(output/shot['file']))
        painter.drawImage(QtCore.QRect(i%2*960, i//2*540, 960, 540), image)
    painter.end()
    sheet.save(str(output/'overview.png'))
    value = dict(schema='j_v5_offline_preview/1', source='OFFLINE_SYNTHETIC_NOT_BOARD_MEASUREMENT',
                 hardware_connected=False, button_count=len(window.live_actions), feature_entry_count=len(FEATURES),
                 screenshots=shots, errors=list(window.data_errors),
                 readiness='LIVE_ONLY_UI_CHECK; not a board acceptance or full feature completion')
    path = output/'preview.json'
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    Path(str(path)+'.sha256').write_text(hashlib.sha256(path.read_bytes()).hexdigest()+'  preview.json\n')
    window.close()
    print(json.dumps(value, ensure_ascii=False))
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connect', help='Only connect; does not start a scene')
    parser.add_argument('--legacy', action='store_true', help='Open the retained J5 fallback window')
    parser.add_argument('--preview-dir', type=Path, help='New output directory for four synthetic live-action previews')
    args = parser.parse_args()
    if args.preview_dir:
        preview(args.preview_dir)
        return 0
    if args.legacy:
        from sentinel_host.product import Window
    else:
        from sentinel_host.application_v61 import Window
    app = app_instance()
    window = Window() if args.legacy else Window(ROOT)
    window.show()
    if args.connect:
        window.address.setText(args.connect)
        window.connect_board()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
