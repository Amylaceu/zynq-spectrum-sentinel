"""Isolated receive-only I2 integration; frozen PL and installed v2 preserved.

prepare packages software only. test shows real Qt windows, walks the four
implemented scenes three times, then leaves FM visible for user inspection.
Unsupported scenes stay disabled. Password is read from stdin, never saved.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

from run_x1_board import ROOT, OPTIONS
from x2_transport import Transport, REMOTE, PYTHON, verified

sys.path[:0] = [str(ROOT), str(ROOT/'src/ps'), str(ROOT/'tools/host')]
from sentinel.release_support import write_result, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'test'))
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--s1-confirmed', action='store_true', required=True)
    args = parser.parse_args()
    if sys.stdin.isatty():
        from getpass import getpass
        password = getpass('Board sudo password (not saved): ')
    else:
        password = sys.stdin.readline().rstrip('\r\n')
    if not password:
        parser.error('Missing sudo credential on stdin')
    class Tee:
        def __init__(self, original, log):
            self.original, self.log = original, log
        def write(self, value):
            self.log.write(value)
            self.log.flush()
            return self.original.write(value)
        def flush(self):
            self.original.flush()
            self.log.flush()
    log = (ROOT/'logs'/('I2_%s_r%d.log' % (args.action, args.attempt))).open('x', encoding='utf-8')
    sys.stdout = Tee(sys.stdout, log)
    transport = Transport(password=password)
    candidate = 'i2_r%d' % args.attempt
    remote = REMOTE+'/release/'+candidate
    if args.action == 'prepare':
        from release_board import build, deploy
        archive = build(ROOT/'build'/('i2_candidate_r%d' % args.attempt))
        result = deploy(archive, password=password, candidate=candidate)
        write_result(ROOT/'board/measurements'/('i2_deployment_r%d.json' % args.attempt), result)
        print(json.dumps(result), flush=True)
        return
    deployment = verified(ROOT/'board/measurements'/('i2_deployment_r%d.json' % args.attempt))
    if deployment.get('status') != 'INSTALLED_HASH_VERIFIED' or deployment.get('root') != remote:
        raise RuntimeError('Exact deployed I2 candidate required')
    output = ROOT/'board/measurements'/('i2_board_r%d' % args.attempt)
    output.mkdir(exist_ok=False)
    result = dict(schema='i2_integration/1', status='STARTED', candidate=remote,
        host_utc=datetime.now(timezone.utc).isoformat(), antenna='S1', tx_requested=False,
        supported_scenes=['check', 'fm', 'listen', 'perf'],
        unsupported=['pano pending I5', 'wifi pending I4', 'ota fallback pending I6'],
        human='PENDING', loops=[], errors=[])

    def postflight():
        loaded = transport.ssh([PYTHON, '-c',
            "import os; os.environ['XILINX_XRT']='/usr'; from pynq import PL; print(PL.bitfile_name)"], privileged=True).strip()
        if not (loaded.startswith(REMOTE+'/release/') and
                loaded.endswith('/overlay/sentinel_v2_100m/sentinel_v2_100m.bit')):
            raise RuntimeError('Unexpected PL image path')
        return json.loads(transport.ssh([PYTHON, '-I', remote+'/scripts/y3_postflight.py',
                                        '--bit', loaded], privileged=True))

    thread = None
    window = None
    service_errors = []
    def service():
        try:
            with (output/'board.log').open('x', encoding='utf-8') as log:
                def line(value):
                    log.write(value)
                    log.flush()
                    print(value, end='', flush=True)
                transport.ssh_lines([PYTHON, '-I', remote+'/scripts/release_entry.py',
                    'serve', '--seconds', '300', '--hostlink'], line, privileged=True, timeout=350)
        except BaseException as error:
            service_errors.append(repr(error))

    try:
        result['preflight'] = postflight()
        if result['preflight']['status'] != 'PASS':
            raise RuntimeError('Stopped preflight required')
        from PySide6 import QtCore, QtWidgets
        from sentinel_host.shell import Window
        from sentinel_host.theme import configure
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        configure(app)
        window = Window()
        window.show()
        thread = threading.Thread(target=service, daemon=True)
        thread.start()
        window.start_worker(address=transport.target.split('@')[-1])
        begin = time.monotonic()
        # Explicit application pump keeps Qt network/render ownership on main.
        def pump(seconds):
            until = time.monotonic()+seconds
            while time.monotonic() < until:
                app.processEvents()
                if service_errors:
                    raise RuntimeError(str(service_errors))
                time.sleep(.005)
        while window.model.hello.get('mode') != 'resident':
            pump(.1)
            if time.monotonic()-begin > 70:
                raise TimeoutError('Resident hello not received')
        result['hello'] = dict(window.model.hello)
        window.presentation.toggle()
        scene_sequence = [0, 2, 3, 6]*3
        for index, scene in enumerate(scene_sequence):
            if index:
                window.presentation.request(scene)
            deadline = time.monotonic()+20
            while window.presentation.pending:
                pump(.05)
                if time.monotonic() > deadline:
                    raise TimeoutError('Matching scene reply missing')
            if window.presentation.state != 'READY':
                raise RuntimeError('Scene not ready: '+window.presentation.banner.text())
            result['loops'].append(dict(index=index, scene=window.presentation.scenes[scene]['id'],
                page=window.active_page, event=window.presentation.records[-1]))
            print('I2_SCENE_READY '+json.dumps(result['loops'][-1]), flush=True)
            pump(1.)
        window.presentation.request(2)
        deadline = time.monotonic()+15
        while window.presentation.pending and time.monotonic() < deadline:
            pump(.1)
        window.presentation.dialog.hide()
        app.processEvents()
        result['twin_width_px'] = window.twin_canvas.viewport().width()
        window.grab().save(str(output/'projector.png'))
        window.presentation.dialog.grab().save(str(output/'presenter.png'))
        window.presentation.dialog.show()
        print('I2_HUMAN_OBSERVATION_READY', flush=True)
        # A bounded inspection interval; no one-hour stability claim.
        pump(100.)
        result['gui_errors'] = list(window.data_errors)
        result['presentation_events'] = list(window.presentation.records)
        result['received_spectra'] = window.model.spectrum_count
        result['gui_duration_s'] = time.monotonic()-begin
        result['status'] = ('PARTIAL_RECEIVE_PRESENTER_PASS' if not window.data_errors
            and len(result['loops']) == 12 and result['twin_width_px'] >= 1100 else 'FAIL')
    except BaseException as error:
        result.update(status='FAIL', error=repr(error))
    finally:
        if window:
            window.close()
        if thread and thread.is_alive():
            try:
                result['stop'] = json.loads(transport.ssh([PYTHON, '-I',
                    remote+'/scripts/release_entry.py', 'stop'], privileged=True, timeout=25))
                thread.join(45)
                if thread.is_alive():
                    raise TimeoutError('Resident still stopping; do not reset board')
            except BaseException as error:
                result.update(status='FAIL_STOP', stop_error=repr(error))
        try:
            result['postflight'] = postflight()
            if result['postflight']['status'] != 'PASS':
                raise RuntimeError('Stopped readback did not pass')
            for folder in ('measurements', 'logs'):
                subprocess.run(['scp', *OPTIONS, '-r', transport.target+':'+remote+'/'+folder,
                    str(output/folder)], check=True, timeout=90, capture_output=True)
            result['files_sha256'] = {}
            for sidecar in (output/'measurements').rglob('*.sha256'):
                path = Path(str(sidecar)[:-7])
                if sha(path) != sidecar.read_text().split()[0]:
                    raise RuntimeError('Returned evidence hash mismatch')
                result['files_sha256'][path.relative_to(output).as_posix()] = sha(path)
        except BaseException as error:
            result.update(status='FAIL_EVIDENCE_OR_STOP', evidence_error=repr(error))
        result['service_errors'] = service_errors
        if service_errors:
            result['status'] = 'FAIL_SERVICE'
        write_result(output/'acceptance.json', result)
        print(json.dumps({k: v for k, v in result.items() if k not in ('files_sha256', 'presentation_events', 'loops')}), flush=True)


if __name__ == '__main__':
    main()
