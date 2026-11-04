"""Deploy isolated J6 software, exercise real controls and save live Qt screenshots.

Read one optional sudo credential from stdin. Never log/store that credential.
No transmit operation. Existing accepted software candidate remains untouched.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'tools/host'), str(ROOT/'src/ps')]
from sentinel.release_support import write_result, sha
from x2_transport import Transport, PYTHON, OPTIONS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--round', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--sudo-stdin', action='store_true')
    parser.add_argument('--only', nargs='*')
    parser.add_argument('--candidate', choices=('j6_dma_r1',))
    args = parser.parse_args()
    password = sys.stdin.readline().rstrip('\r\n') if args.sudo_stdin else None
    transport = Transport(password)
    identity = args.candidate or 'j6_r%d' % args.round
    output = ROOT/'board/measurements'/identity
    output.mkdir(exist_ok=False)
    from release_board import build, deploy
    archive = ROOT/'build'/identity/'release_v2.tar.gz'
    if not archive.exists(): archive = build(ROOT/'build'/identity)
    deployment = deploy(archive, password=password, candidate=identity)
    remote = deployment['root']
    errors = []
    ready = threading.Event()
    log = (ROOT/'logs'/('J6_service_'+identity+'.log')).open('w', encoding='utf-8')
    def serve():
        try:
            def line(text):
                log.write(text); log.flush()
                if 'J6_READY' in text: ready.set()
            transport.ssh_lines([PYTHON, '-I', remote+'/scripts/serve_features_j6.py',
                '--out', remote+'/measurements/live', '--hostlink-bind', '192.168.2.99',
                '--seconds', '1800'], line, privileged=True, timeout=1860)
        except BaseException as error:
            errors.append(repr(error)); print('SERVICE_ERROR '+repr(error), flush=True); ready.set()
        finally: log.close()
    thread = threading.Thread(target=serve, daemon=True); thread.start()
    if not ready.wait(75) or errors: raise RuntimeError('Service startup: '+str(errors))
    from product import app_instance
    from sentinel_host.features_v6 import Window, CARDS
    app = app_instance(); window = Window(ROOT); window.show()
    window.connect_board()
    def pump(seconds, until=lambda: False):
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline and not until():
            app.processEvents(); time.sleep(.01)
        app.processEvents()
    pump(10, lambda: bool(window.model.hello))
    if not window.model.hello: raise RuntimeError('Host hello timeout')
    summary = dict(round=args.round, source='CURRENT_BOARD_LIVE_NOT_SYNTHETIC',
        deployment=deployment, tests=[], sequential=[], historical_failures_preserved=True,
        bit_sha256=window.model.hello.get('bit_sha256'))
    selected = args.only or [key for key, _, _ in CARDS]
    try:
        for key in selected:
            count = len(window.results)
            window.start_feature(key)
            pump(13 if key == 'F10' else 8, lambda: len(window.results) > count)
            if len(window.results) == count: raise TimeoutError('No feature response: '+key)
            start = window.results[-1]
            pump(.5)
            path = output/(key+'_comparison.png')
            window.grab().save(str(path))
            count = len(window.results)
            window.stop_feature(); pump(5, lambda: len(window.results) > count)
            stop = window.results[-1] if len(window.results) > count else {}
            passed = (start.get('status') == 'READY' and start.get('within_target') is True
                and stop.get('status') == 'STOPPED' and stop.get('restored') is True)
            record = dict(id=key, status='PASS' if passed else 'FAIL', start=start, stop=stop,
                screenshot=path.name, screenshot_sha256=sha(path))
            summary['tests'].append(record); write_result(output/'acceptance.json', summary)
            print(key+' '+record['status']+' '+str(start.get('error', start.get('elapsed_s'))), flush=True)
        for record in summary['tests']:
            if record['status'] != 'PASS': continue
            count = len(window.results); window.start_feature(record['id'])
            pump(13 if record['id'] == 'F10' else 8, lambda: len(window.results) > count)
            response = window.results[-1] if len(window.results) > count else {}
            summary['sequential'].append(response)
        count = len(window.results); window.stop_feature(); pump(5, lambda: len(window.results) > count)
        summary['final_stop'] = window.results[-1]
        summary['gui_errors'] = window.data_errors
        expected = [x['id'] for x in summary['tests'] if x['status'] == 'PASS']
        sequence_ok = (len(summary['sequential']) == len(expected) and all(
            x.get('id') == key and x.get('status') == 'READY' and x.get('within_target')
            for key, x in zip(expected, summary['sequential'])))
        summary['sequence_passed'] = sequence_ok
        summary['service_errors'] = list(errors)
        summary['status'] = ('FAIL_CONTINUOUS_SEQUENCE' if not sequence_ok or errors or window.data_errors
            or summary['final_stop'].get('status') != 'STOPPED' else
            'COMPLETE_WITH_UNAVAILABLE' if len(expected) != len(selected) else 'PASS')
        write_result(output/'acceptance.json', summary)
        for record in summary['tests']:
            if record['status'] != 'PASS': window.cards[record['id']][0].hide()
        print('J6_CHECK_COMPLETE '+summary['status'], flush=True)
        # Keep the real window available to the user, service bounded at 30 minutes.
        app.exec()
    finally:
        write_result(output/'host_session.json', dict(results=window.results, errors=window.data_errors, service_errors=errors))


if __name__ == '__main__': main()
