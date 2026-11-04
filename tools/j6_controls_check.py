"""Verify CFAR controls, target picking and replay/capture reuse on current board."""
import json
import argparse
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tools/host'), str(ROOT/'src/ps')]
from product import app_instance
from sentinel_host.features_v6 import Window
from sentinel.release_support import write_result, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    app = app_instance(); window = Window(ROOT); window.show(); window.connect_board()
    out = args.output; out.mkdir(parents=True, exist_ok=False)
    def pump(seconds, until=lambda: False):
        end = time.monotonic()+seconds
        while time.monotonic() < end and not until(): app.processEvents(); time.sleep(.01)
        app.processEvents()
    def start(key):
        n = len(window.results); window.start_feature(key); pump(12, lambda: len(window.results)>n)
        if len(window.results) <= n or window.results[-1].get('status') != 'READY': raise RuntimeError('Start failed: '+key)
        return window.results[-1]
    result = dict(source='CURRENT_BOARD', controls=[])
    try:
        pump(8, lambda: bool(window.model.hello))
        for mode, alpha in (('GO', 256), ('SO', 8192), ('CA', 1974)):
            window.cfar_mode.blockSignals(True); window.cfar_mode.setCurrentText(mode); window.cfar_mode.blockSignals(False)
            window.alpha.setValue(alpha)
            record = start('F5')
            if record['readback']['alpha'] != alpha or record['readback']['cfar_ctrl'] != {'CA':1, 'GO':3, 'SO':5}[mode]: raise RuntimeError('CFAR register mismatch')
            pump(.3); shot=out/('F5_'+mode+'.png'); window.grab().save(str(shot))
            result['controls'].append(dict(result=record, screenshot=shot.name, sha256=sha(shot)))
        # Replay's global DMA reset must not invalidate the subsequent IQ capture.
        for key in ('F9', 'F7', 'F10', 'F7'):
            record = start(key); pump(.7)
            result['controls'].append(dict(result=record))
        pump(.5)
        if not window.model.targets: raise RuntimeError('No live target for F7 selection')
        target = window.model.targets[0]
        sequence = window.worker.command('select_target', key=target['key'])
        before = window.last_result.get('channel', {}).get('frequency_hz')
        pump(3, lambda: window.last_result.get('channel', {}).get('frequency_hz') == target['frequency_hz'])
        if window.last_result.get('channel', {}).get('frequency_hz') != target['frequency_hz']: raise RuntimeError('Channel target selection not applied')
        shot=out/'F7_selected.png'; window.grab().save(str(shot))
        result['selected'] = dict(key=target['key'], frequency_hz=target['frequency_hz'], channel=window.last_result['channel'], screenshot=shot.name, sha256=sha(shot))
        n=len(window.results); window.stop_feature(); pump(5, lambda: len(window.results)>n)
        result['stop'] = window.results[-1]
        result['status'] = 'PASS' if result['stop'].get('status') == 'STOPPED' and not window.data_errors else 'FAIL'
    except Exception as error:
        result.update(status='FAIL', error=repr(error))
    finally:
        if window.active:
            n=len(window.results); window.stop_feature(); pump(5, lambda: len(window.results)>n)
        result['gui_errors'] = window.data_errors
        write_result(out/'result.json', result)
        window.close(); app.processEvents()
    print(json.dumps(result, ensure_ascii=True), flush=True)


if __name__ == '__main__': main()
