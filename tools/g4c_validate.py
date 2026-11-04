"""Receive-only G4c validation with unchanged deployed software and frozen PL."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'src/ps')]
from g3_validate import launch, completed
from fetch_release_evidence import fetch
from run_x1_board import write_evidence, sha
from x2_transport import Transport, REMOTE, PYTHON


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sudo-stdin', required=True, action='store_true')
    p.add_argument('--attempt', type=int, choices=(1,2,3), default=1)
    p.add_argument('--seconds', type=int, choices=range(90,601), default=180)
    a = p.parse_args()
    t = Transport(password=sys.stdin.readline().rstrip('\r\n'))
    name = 'g4c_board_r%d' % a.attempt
    output = ROOT/'board/measurements'/name
    output.mkdir(exist_ok=False)
    root = REMOTE+'/release/v2'
    result = dict(configuration='A', tx_requested=False, status='STARTED',
                  deployed_release_changed=False, audio='NOT_TESTED')
    child = None
    try:
        launch(t, name, a.seconds+90, True)
        address = t.target.rsplit('@',1)[-1]
        deadline = time.monotonic()+90
        while True:
            try:
                with socket.create_connection((address,9000), timeout=2):
                    break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(1)
        env = dict(os.environ)
        env.pop('QT_QPA_PLATFORM', None)
        child = subprocess.Popen([sys.executable,str(ROOT/'tools/host/g4c_live_probe.py'),
            '--address',address,'--output',str(output),'--seconds',str(a.seconds)],cwd=ROOT,env=env)
        print('G4C_GUI_STARTED',child.pid,flush=True)
        child.wait(timeout=a.seconds+45)
        if child.returncode:
            raise RuntimeError('GUI exited %d' % child.returncode)
        result['gui'] = json.loads((output/'gui_metrics.json').read_text(encoding='utf-8'))
        result['status'] = 'MEASURED'
    except BaseException as error:
        result.update(status='FAIL',error=repr(error))
        raise
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            child.wait(timeout=10)
        try:
            result['stop'] = t.ssh(['sh',root+'/scripts/sentinel.sh','stop'],privileged=True)
            result['postflight'] = json.loads(t.ssh([PYTHON,'-I',root+'/scripts/y3_postflight.py',
                '--bit',root+'/overlay/sentinel_v2_100m/sentinel_v2_100m.bit'],privileged=True))
            tag = completed(t,name,60)
            result['tag'] = tag
            fetch(tag,'monitor',output/'board_raw')
        except BaseException as error:
            result['cleanup_error'] = repr(error)
        result['files_sha256'] = {str(f.relative_to(output)):sha(f)
            for f in output.rglob('*') if f.is_file()}
        write_evidence(output/'validation.json',result)
    print('G4C_VALIDATION_COMPLETE',flush=True)


if __name__ == '__main__':
    main()
