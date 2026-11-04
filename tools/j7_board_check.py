"""Exercise J7 via the actual Qt controls and single resident hardware owner."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tools/host'), str(ROOT/'tools'), str(ROOT/'src/ps')]
from product import app_instance
from sentinel_host.application_v61 import Window, APP_IDS
from sentinel.release_support import write_result, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--only', nargs='+', default=['F0','F1','F2','F4','F5','F6','F7','F10','F8','F11','F12','F13'])
    parser.add_argument('--search', action='store_true')
    parser.add_argument('--search-before-f12', action='store_true')
    parser.add_argument('--fullscreen', action='store_true')
    parser.add_argument('--record-cycles', type=int, choices=range(4), default=0)
    parser.add_argument('--enable-recording-candidate', action='store_true',
                        help='Expose the isolated finite-recording candidate for this test process only')
    parser.add_argument('--record-frequency', type=int, default=0,
                        help='FM frequency in Hz; zero uses this run\'s automatic choice')
    parser.add_argument('--keep-window', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    if args.enable_recording_candidate:
        import sentinel_host.application_v61 as application
        application.RECORDING_AVAILABLE = True
        application.RECORDING_UNAVAILABLE = ''
    app = app_instance(); window = Window(ROOT); window.show(); window.connect_board()
    if args.fullscreen: window.showFullScreen()
    report = dict(source='CURRENT_BOARD', tests=[], search=None, recordings=[], historical_failures_preserved=True)

    def save():
        report['gui_errors'] = list(window.data_errors)
        write_result(args.output/'result.json', report)

    def pump(seconds, until=lambda: False):
        end = time.monotonic()+seconds
        while time.monotonic() < end and not until():
            app.processEvents(); time.sleep(.01)
        app.processEvents()

    def begin(key, action='start', frequency=None, wait=180):
        before = len(window.results)
        window.start_feature(key, action=action, frequency=frequency)
        pump(wait, lambda: len(window.results) > before and not window.pending and not window.app_busy)
        if len(window.results) <= before or window.app_busy: raise TimeoutError('Application not finished: '+key+'/'+action)
        value = window.results[-1]
        if value.get('status') in ('FAILED', 'CANCELLED'):
            report.setdefault('rejected_commands', []).append(dict(id=key, action=action, result=value))
            save()
            raise RuntimeError('Application rejected: '+str(value))
        return value

    def stop():
        before = len(window.results); window.stop_feature()
        pump(10, lambda: len(window.results) > before and not window.pending)
        if len(window.results) <= before: raise TimeoutError('Stop not acknowledged')
        value = window.results[-1]
        if value.get('status') != 'STOPPED' or not value.get('restored'):
            raise RuntimeError('Restoration failed: '+str(value))
        return value

    def shot(name):
        path = args.output/(name+'.png'); window.grab().save(str(path))
        return dict(file=path.name, sha256=sha(path))

    def twin_shot(name):
        from PIL import Image
        from sentinel_host.twin import rgb888
        path = args.output/(name+'_lcd_twin.png')
        Image.fromarray(rgb888(window.twin.render())).save(path)
        return dict(file=path.name, sha256=sha(path),
                    ui_frames_received=window.twin.ui_count,
                    scope='PS pixels from applied LCD bank; PL sampled reconstruction')

    try:
        pump(10, lambda: bool(window.model.hello))
        if not window.model.hello: raise ConnectionError('No board hello')
        report['bit_sha256'] = window.model.hello.get('bit_sha256')
        for key in args.only:
            if key == 'F12' and args.search_before_f12:
                report['search'] = begin('F8', 'search', wait=180)
                report['search_screenshot'] = shot('F8_search')
                report['search_stop'] = stop(); save()
            value = begin(key)
            pump(4 if key == 'F2' else 1.2)
            record = dict(id=key, result=value, screenshot=shot(key), lcd=twin_shot(key),
                comparison=[window.table.item(i, 0).text() for i in range(window.table.rowCount())],
                navigation_scroll_maximum=window.nav_scroll.verticalScrollBar().maximum())
            window.toggle_twin(); pump(.1)
            record['twin_page'] = window.tabs.currentIndex()
            window.toggle_twin()
            if key == 'F2':
                record['fps_samples'] = [t.get('display_fps') for _, t in window.model.telemetry if t.get('scene') == key][-2:]
                record['fps_pass'] = bool(record['fps_samples']) and min(record['fps_samples']) >= 25
            record['stop'] = stop(); report['tests'].append(record); save()
            print(key, value['status'], value.get('error', value.get('elapsed_s')), flush=True)
        if args.search:
            report['search'] = begin('F8', 'search', wait=180)
            report['search_screenshot'] = shot('F8_search'); save()
            print('SEARCH', json.dumps(report['search'].get('stations', [])), flush=True)
            for station in report['search'].get('stations', [])[:3]:
                value = begin('F8', frequency=station['frequency_hz'])
                pump(5)
                report['tests'].append(dict(id='F8_TUNE', frequency_hz=station['frequency_hz'],
                    result=value, screenshot=shot('F8_'+str(station['frequency_hz'])), stop=stop()))
                save()
                print('TUNE', station['frequency_hz'], value['status'], value.get('error'), flush=True)
        for cycle in range(args.record_cycles):
            live = begin('F8', frequency=args.record_frequency); pump(2)
            if cycle == 1:
                from PySide6 import QtCore
                QtCore.QTimer.singleShot(4200, window.stop_recording)
            value = begin('F8', 'record', wait=60)
            if value['status'] != 'DONE':
                report['recordings'].append(dict(cycle=cycle+1, result=value)); save()
                raise RuntimeError('Recording rejected: '+str(value.get('error')))
            pump(180, lambda: window.audio_worker is not None and not window.audio_worker.isRunning())
            if not window.current_audio: raise RuntimeError('No validated audio: '+window.app_caption.text())
            window.play_recording(); pump(12)
            record = dict(cycle=cycle+1, result=value, audio=window.current_audio,
                screenshot=shot('F8_record_%d' % (cycle+1)), pc_playback_started=True,
                listening='PENDING_USER', pc_player_error=window.audio_dialog.player.errorString())
            window.audio_dialog.close(); window.audio_dialog=None
            before = len(window.results); window.return_live()
            pump(30, lambda: len(window.results) > before and not window.pending and not window.app_busy)
            if len(window.results) <= before or window.results[-1].get('status') != 'DONE':
                raise RuntimeError('Return to live broadcast failed: '+str(window.last_result))
            record['returned_live'] = window.results[-1]; pump(3)
            record['stop'] = stop(); report['recordings'].append(record); save()
            print('RECORDING_CYCLE', cycle+1, value['status'], flush=True)
        report['status'] = 'CHECKS_COMPLETED'; report['final_stop'] = stop(); save()
        print('J7_CHECKS_COMPLETED', flush=True)
    except Exception as error:
        report.update(status='FAIL', error=repr(error)); save(); print('J7_CHECK_FAILED', repr(error), flush=True)
        try: report['final_stop'] = stop(); save()
        except Exception as stop_error: report['stop_error'] = repr(stop_error); save()
    if args.keep_window:
        app.exec()
    else:
        window.close(); app.processEvents()


if __name__ == '__main__': main()
