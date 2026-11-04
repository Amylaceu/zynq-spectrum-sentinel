import argparse
import json
import sys
import time

from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets
from .shell import Window
from .theme import configure


def main():
    p = argparse.ArgumentParser(description='Spectrum Sentinel desktop client')
    p.add_argument('--connect', help='Board LAN IPv4')
    p.add_argument('--replay', help='Verified .zsr directory')
    p.add_argument('--preview', help='Save a deterministic OFFLINE screenshot and exit')
    p.add_argument('--record', help='Create a new .zsr recording')
    p.add_argument('--panorama', help='Open a SHA256-verified F4 result.json (stored snapshots)')
    p.add_argument('--panorama-live', help='Tail provisional pano_tile JSONL from an active scan')
    p.add_argument('--panorama-final', help='Verify final scan result when it has been fetched')
    p.add_argument('--auto-exit', type=float, help='Bounded automated run in seconds')
    p.add_argument('--evidence', help='Write actual GUI process metrics JSON and SHA256')
    p.add_argument('--screenshot-out', help='Capture GUI before automated close')
    p.add_argument('--present', action='store_true', help='Open presenter controls; never transmits')
    args = p.parse_args()
    app = QtWidgets.QApplication(sys.argv[:1])
    # Offscreen Qt on Windows does not discover system fonts automatically.
    if not QtGui.QFontDatabase.families():
        for directory in QtCore.QStandardPaths.standardLocations(QtCore.QStandardPaths.FontsLocation):
            for name in ('msyh.ttc', 'msyhbd.ttc', 'consola.ttf', 'segoeui.ttf', 'arial.ttf', 'DejaVuSans.ttf'):
                path = Path(directory)/name
                if path.is_file():
                    QtGui.QFontDatabase.addApplicationFont(str(path))
    configure(app)
    window = Window()
    window.show()
    if args.panorama:
        window.load_panorama(args.panorama)
    if args.panorama_live:
        from .panorama_live import ProgressTail
        tail = ProgressTail(args.panorama_live)
        panels = [window.panorama_panel]+sum(window.panel_groups[4], [])
        window.select_page(4, manual=True)
        live_timer = QtCore.QTimer(window)
        def progress():
            try:
                for packet in tail.poll():
                    for panel in panels:
                        panel.apply_tile(packet)
                if args.panorama_final:
                    final = Path(args.panorama_final)
                    receipt = final.parent.parent/'validation.json'
                    if receipt.exists() and Path(str(receipt)+'.sha256').exists():
                        from .panorama_data import checked
                        value = json.loads(checked(receipt).read_text(encoding='utf-8'))
                        if value.get('status') != 'PASS_SNAPSHOT_SCAN':
                            raise ValueError('扫描退出或独立停止检查未通过')
                        window.load_panorama(final)
                        live_timer.stop()
            except (OSError, ValueError, KeyError, IndexError) as error:
                window.data_errors.append('全景进度: '+str(error))
                for panel in panels:
                    panel.state.setText('全景校验停止：'+str(error))
                live_timer.stop()
        live_timer.timeout.connect(progress)
        live_timer.start(100)
    if args.connect:
        window.address.setText(args.connect)
        window.connect_board()
    if args.replay:
        window.start_worker(session=args.replay)
    if args.present:
        QtCore.QTimer.singleShot(1500, window.presentation.toggle)
    if args.record:
        from .session import Recorder
        window.recorder=Recorder(args.record,source='replay' if args.replay else 'live')
    if args.auto_exit:
        import hashlib
        import statistics
        import psutil
        proc=psutil.Process()
        proc.cpu_percent()
        samples=[]
        finished=[False]
        start=time.monotonic()
        def measure():
            samples.append(dict(elapsed_s=time.monotonic()-start,
                rss_bytes=proc.memory_info().rss,cpu_single_core_pct=proc.cpu_percent(),
                spectra=window.model.spectrum_count,painted=window.painted_frames,
                errors=list(window.data_errors)))
        metrics=QtCore.QTimer(window)
        metrics.timeout.connect(measure)
        metrics.start(1000)
        def finish():
            if finished[0]:
                return
            finished[0] = True
            measure()
            elapsed=time.monotonic()-start
            if args.screenshot_out:
                window.grab().save(args.screenshot_out)
            window.stop_worker()
            if window.recorder:
                window.recorder.close();window.recorder=None
            if args.evidence:
                warm=[s for s in samples if s['elapsed_s']>=10]
                first=warm[0] if warm else samples[0]
                last=samples[-1]
                span=max(.001,last['elapsed_s']-first['elapsed_s'])
                value=dict(schema='g4_gui_metrics/1',source='replay' if args.replay else 'live',
                    duration_s=elapsed,samples=samples,errors=window.data_errors,
                    received_spectra=window.model.spectrum_count,painted_frames=window.painted_frames,
                    received_hz=(last['spectra']-first['spectra'])/span,
                    paint_hz=(last['painted']-first['painted'])/span,
                    memory_growth_bytes=max(s['rss_bytes'] for s in warm or samples)-first['rss_bytes'],
                    cpu_single_core_median_pct=statistics.median(s['cpu_single_core_pct'] for s in warm or samples),
                    cpu_machine_median_pct=statistics.median(s['cpu_single_core_pct'] for s in warm or samples)/(psutil.cpu_count() or 1),
                    receive_to_update_median_ms=statistics.median(window.latencies) if window.latencies else None,
                    latency_scope='PC socket receive to Qt setData; not PL-to-screen or optical scanout',
                    pl_to_screen_latency='NOT_CERTIFIED',recording=args.record,
                    final_targets=window.model.targets,final_events=list(window.model.events))
                value.update(twin_pl_frames=window.twin.pl_count, twin_ui_frames=window.twin.ui_count,
                    twin_painted_frames=window.twin_painted, twin_epoch=window.twin.epoch)
                value.update(presentation_events=window.presentation.records,
                    presentation_state=window.presentation.state,
                    presentation_twin_width_px=window.twin_canvas.viewport().width())
                if args.panorama_live:
                    value.update(panorama_progress_source=args.panorama_live,
                        panorama_live_tiles=len(window.panorama_panel.live.tiles),
                        panorama_verified_result=window.panorama_panel.loaded_path,
                        measurement_scope='provisional finite snapshot progress then SHA-verified stored scan')
                path=Path(args.evidence)
                if path.exists():
                    raise FileExistsError('Preserve metrics evidence')
                path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')
                Path(str(path)+'.sha256').write_text(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name+'\n')
            window.close()
        QtCore.QTimer.singleShot(int(args.auto_exit*1000),finish)
        app.aboutToQuit.connect(finish)
    if args.preview:
        import numpy as np
        header = dict(type='spectrum',lo_hz=96050000,frequency_start_hz=94130000,bin_spacing_hz=3750)
        x = np.arange(1024)
        values = (np.full(1024,30.)+30*np.exp(-((x-445)/8)**2))*100
        window.model.apply(header, values.astype('<i2').tobytes())
        window.title.setText('OFFLINE / SYNTHETIC PREVIEW — not a board measurement')
        window.refresh()
        def save():
            window.grab().save(args.preview)
            window.close()
        QtCore.QTimer.singleShot(500, save)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
