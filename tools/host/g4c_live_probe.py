"""Bounded real-window G4c probe; only safe tab/NEXT mouse clicks.

No RF ownership here. tools/g4c_validate.py owns launch and final cleanup.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'src/ps'), str(ROOT/'tools/host'), str(ROOT/'tools')]
from PySide6 import QtCore, QtWidgets
from PySide6.QtTest import QTest
import numpy as np
import psutil
from sentinel_host.shell import Window
from sentinel_host.session import Recorder
from sentinel_host.theme import configure
from run_x1_board import write_evidence


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--address', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seconds', type=int, default=180)
    a = p.parse_args()
    if os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
        p.error('Live validation requires a visible desktop window')
    app = QtWidgets.QApplication([])
    configure(app)
    window = Window()
    window.show()
    window.address.setText(a.address)
    window.connect_board()
    window.recorder = Recorder(a.output/'live_A.zsr', source='live')
    start = time.monotonic()
    proc = psutil.Process()
    proc.cpu_percent()
    counts, samples, clicks, replies, geometry = Counter(), [], [], [], []
    applied = {}
    wire = (a.output/'wire.jsonl').open('x', encoding='utf-8')

    def packet(header, payload, received):
        kind = header['type']
        counts[kind] += 1
        wire.write(json.dumps(dict(header=header, host_received_mono=received,
            payload_sha256=hashlib.sha256(payload).hexdigest()))+'\n')
        if kind == 'reply':
            replies.append(header)
            for click in clicks:
                if 'reply' not in click:
                    click['reply'] = header
                    break
        if kind == 'ui_frame' and header.get('request'):
            applied.setdefault(header['request'][1], (received, header['epoch']))
        for click in clicks:
            seq = click.get('reply', {}).get('request_seq')
            if seq in applied and 'sent_mono' in click:
                click.setdefault('applied_ms', 1000*(applied[seq][0]-click['sent_mono']))
                click.setdefault('epoch', applied[seq][1])

    window.worker.packet.connect(packet)

    def measure():
        samples.append(dict(elapsed_s=time.monotonic()-start,
            rss_bytes=proc.memory_info().rss, cpu_single_core_pct=proc.cpu_percent(),
            pl_frames=window.twin.pl_count, ui_frames=window.twin.ui_count,
            painted=window.twin_painted, spectra=window.model.spectrum_count))

    def click(index):
        if not window.twin.ui_count:
            clicks.append(dict(skipped='No live UI yet', index=index))
            return
        if index == 3:
            window.toggle_focus()
            app.processEvents()
        if index == 6:
            if window.focused:
                window.toggle_focus()
            window.select_page(0, manual=True)
            return
        x, y = ((600, 12), (680, 12), (760, 12))[index % 3]
        rect = window.twin_canvas.viewport()
        point = QtCore.QPoint(round(rect.x()+(x+.5)*rect.width()/800),
                             round(rect.y()+(y+.5)*rect.height()/480))
        mapped = window.twin_canvas.physical(QtCore.QPointF(point))
        record = dict(index=index, sent_mono=time.monotonic(),
            intended=[x, y], mapped=list(mapped) if mapped else None,
            expected_action=('tab:SIG', 'tab:TGT', 'tab:STAT')[index % 3],
            viewport=[rect.width(), rect.height()], scale=rect.width()/800)
        clicks.append(record)
        geometry.append(dict(focused=window.focused, window=[window.width(),window.height()],
                             viewport=[rect.width(),rect.height()]))
        QTest.mouseClick(window.twin_canvas, QtCore.Qt.MouseButton.LeftButton, pos=point)
        print('LIVE_MOUSE_CLICK', json.dumps(record), flush=True)

    for i in range(7):
        QtCore.QTimer.singleShot(10000+i*3000, lambda i=i: click(i))

    def pages():
        for i in range(7):
            window.select_page(i, manual=True)
            app.processEvents()
        window.select_page(0, manual=True)
        print('USER_VISUAL_READY', flush=True)
    QtCore.QTimer.singleShot(32000, pages)
    timer = QtCore.QTimer(window)
    timer.timeout.connect(measure)
    timer.start(1000)
    finished = [False]

    def finish():
        if finished[0]:
            return
        finished[0] = True
        measure()
        window.grab().save(str(a.output/'live.png'))
        window.stop_worker()
        if window.recorder:
            window.recorder.close()
            window.recorder = None
        wire.close()
        warm = [s for s in samples if s['elapsed_s'] >= 40] or samples
        first, last = warm[0], warm[-1]
        span = max(.001, last['elapsed_s']-first['elapsed_s'])
        cpu = float(np.median([s['cpu_single_core_pct'] for s in warm]))
        result = dict(schema='g4c_live_gui/1', source='live', duration_s=time.monotonic()-start,
            configuration='A', tx_requested=False, geometry=geometry, counts=dict(counts),
            clicks=clicks, replies=replies, samples=samples, errors=window.data_errors,
            received_pl_hz=(last['pl_frames']-first['pl_frames'])/span,
            received_ui_hz=(last['ui_frames']-first['ui_frames'])/span,
            fresh_twin_updates_hz=(last['painted']-first['painted'])/span,
            cpu_single_core_median_pct=cpu, cpu_machine_median_pct=cpu/(psutil.cpu_count() or 1),
            memory_growth_bytes=max(s['rss_bytes'] for s in warm)-first['rss_bytes'],
            refresh_p95_ms=float(np.percentile(window.paint_times,95)),
            page_switch_max_ms=max(window.switch_times),
            timing_scope='Qt refresh callback; excludes compositor and optical scanout',
            audio='NOT_TESTED', long_test_30min='NOT_TESTED', user_visual='PENDING')
        write_evidence(a.output/'gui_metrics.json', result)
        print('G4C_GUI_COMPLETE', flush=True)
        window.close()
    QtCore.QTimer.singleShot(a.seconds*1000, finish)
    app.aboutToQuit.connect(finish)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
