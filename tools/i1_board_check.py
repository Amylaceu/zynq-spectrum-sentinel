"""Build isolated I1 candidate or run bounded receive-only scene measurements.

Credentials: one stdin line only. Never passed in command arguments or saved.
The installed release/v2 is preserved. Each attempt has a new candidate and
measurement directory; no automatic fourth attempt or RF transmission.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import statistics
import subprocess
import sys
import threading
import time

from x2_transport import Transport, REMOTE, PYTHON
from run_x1_board import ROOT, OPTIONS
sys.path.insert(0, str(ROOT/'src/ps'))
from sentinel.release_support import write_result, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'test'))
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--antenna-confirmed', action='store_true', required=True)
    args = parser.parse_args()
    password = sys.stdin.readline().rstrip('\r\n')
    if not password:
        parser.error('Sudo credential required on stdin')
    transport = Transport(password=password)
    candidate = 'i1_r%d' % args.attempt
    remote = REMOTE+'/release/'+candidate
    output = ROOT/'board/measurements'/('i1_board_r%d' % args.attempt)
    if args.action == 'prepare':
        from release_board import build, deploy
        package = ROOT/'build'/('i1_candidate_r%d' % args.attempt)
        archive = build(package)
        result = deploy(archive, password=password, candidate=candidate)
        write_result(ROOT/'board/measurements'/('i1_deployment_r%d.json' % args.attempt), result)
        print(json.dumps(result), flush=True)
        return
    output.mkdir(exist_ok=False)
    bit = remote+'/overlay/sentinel_v2_100m/sentinel_v2_100m.bit'
    result = dict(status='STARTED', host_utc=datetime.now(timezone.utc).isoformat(),
                  configuration='S1', antenna_confirmed=True, transmit_requested=False,
                  candidate=remote, installed_v2_preserved=True,
                  human_listening='PENDING', transitions=[],
                  limitations=['pano/wifi pending I4/I5', 'ota/noise require labelled PC replay',
                               'no transmission or disconnect watchdog test'])
    def postflight():
        # Query PYNQ's loaded path instead of assuming which release last ran.
        script = "import os; os.environ['XILINX_XRT']='/usr'; from pynq import PL; print(PL.bitfile_name)"
        loaded = transport.ssh([PYTHON, '-c', script], privileged=True).strip()
        if not (loaded.startswith(REMOTE+'/release/') and
                loaded.endswith('/overlay/sentinel_v2_100m/sentinel_v2_100m.bit')):
            raise RuntimeError('Unexpected loaded image path: '+loaded)
        return json.loads(transport.ssh([PYTHON, '-I', REMOTE+'/release/v2/scripts/y3_postflight.py',
                                         '--bit', loaded], privileged=True))
    thread = None
    errors = []
    ready = threading.Event()
    # This reader owns only an SSH stream; hardware remains on the board owner thread.
    def run_service():
        try:
            with (output/'board.log').open('x', encoding='utf-8') as log:
                def on_line(line):
                    log.write(line)
                    log.flush()
                    print(line, end='', flush=True)
                    if 'Running serve' in line:
                        ready.set()
                transport.ssh_lines([PYTHON, '-I', remote+'/scripts/release_entry.py',
                    'serve', '--seconds', '360', '--hostlink'], on_line,
                    privileged=True, timeout=420)
        except BaseException as error:
            errors.append(repr(error))
            ready.set()
    def command(*tokens):
        begin = time.monotonic()
        response = json.loads(transport.ssh([PYTHON, '-I', remote+'/scripts/release_entry.py',
                                             *tokens], privileged=True, timeout=25))
        return dict(response=response, ssh_roundtrip_s=time.monotonic()-begin)
    try:
        # Prevent any launch before exact candidate deployment is verified.
        deployment = ROOT/'board/measurements'/('i1_deployment_r%d.json' % args.attempt)
        if sha(deployment) != Path(str(deployment)+'.sha256').read_text().split()[0]:
            raise RuntimeError('Candidate deployment evidence mismatch')
        installed = json.loads(deployment.read_text())
        if installed['status'] != 'INSTALLED_HASH_VERIFIED' or installed['root'] != remote:
            raise RuntimeError('Wrong candidate deployment')
        transport.ssh([PYTHON, '-I', remote+'/scripts/release_entry.py', 'verify'])
        result['preflight'] = postflight()
        if result['preflight']['status'] != 'PASS':
            raise RuntimeError('Independent stopped preflight failed')
        thread = threading.Thread(target=run_service, daemon=True)
        thread.start()
        if not ready.wait(45) or errors:
            raise RuntimeError('Supervisor did not start: '+str(errors))
        # Readiness is an explicit root-only socket, not the supervisor log line.
        deadline = time.monotonic()+60
        while time.monotonic() < deadline:
            if errors or not thread.is_alive():
                raise RuntimeError('Resident exited during startup: '+str(errors))
            test = transport.ssh([PYTHON, '-c',
                "import os,stat; p='/run/zss_resident_v1.sock'; print(int(os.path.exists(p) and stat.S_ISSOCK(os.stat(p).st_mode)))"])
            if test.strip() == '1':
                break
            time.sleep(.3)
        else:
            raise TimeoutError('Resident did not expose control socket')
        result['initial_status'] = command('status')
        scenes = ['check', 'fm', 'listen', 'perf', 'idle']*10
        random.Random(20261104).shuffle(scenes)
        for index, scene in enumerate(scenes):
            measured = command('scene', scene)
            measured.update(index=index, scene=scene)
            result['transitions'].append(measured)
            write_result(output/'progress.json', result)
            print(json.dumps(dict(index=index, scene=scene, **measured['response'])), flush=True)
        result['metrics'] = {}
        for scene in ('check', 'fm', 'listen', 'perf', 'idle'):
            values = [x['response']['result'] for x in result['transitions'] if x['scene'] == scene]
            times = sorted(v.get('ready_s', v.get('elapsed_s', 0)) for v in values)
            result['metrics'][scene] = dict(attempts=len(values),
                ready=sum(v['status'] == 'READY' for v in values),
                p90_s=times[8], median_s=statistics.median(times),
                all_within_target=all(v.get('within_target', False) for v in values),
                scope='Board dispatch to verified readiness; SSH full roundtrip reported separately')
        result['final_status'] = command('status')
        result['stop'] = command('stop')
        thread.join(55)
        if thread.is_alive():
            raise TimeoutError('Graceful supervisor stop still pending; no forced reset')
        if errors:
            raise RuntimeError(str(errors))
        result['status'] = ('PARTIAL_RECEIVE_SCENES_PASS' if all(
            m['ready'] == 10 and m['all_within_target'] for m in result['metrics'].values())
            else 'FAIL_RECEIVE_SCENE_METRICS')
    except BaseException as error:
        result.update(status='FAILED', error=repr(error))
        raise
    finally:
        if thread and thread.is_alive():
            try:
                result['emergency_stop'] = command('stop')
                thread.join(55)
            except BaseException as error:
                result['cleanup_error'] = repr(error)
        try:
            result['postflight'] = postflight()
            # Preserve worker data and supervisor logs from this isolated candidate.
            for folder in ('measurements', 'logs'):
                subprocess.run(['scp', *OPTIONS, '-r', transport.target+':'+remote+'/'+folder,
                    str(output/folder)], check=True, timeout=90, capture_output=True)
            files = {}
            for sidecar in (output/'measurements').rglob('*.sha256'):
                target = Path(str(sidecar)[:-7])
                if not target.is_file() or sha(target) != sidecar.read_text().split()[0]:
                    raise RuntimeError('Returned evidence digest mismatch: '+str(target))
                files[target.relative_to(output).as_posix()] = sha(target)
            result['verified_evidence'] = files
        except BaseException as error:
            result.update(evidence_error=repr(error), status='FAILED_EVIDENCE_OR_STOP')
        write_result(output/'acceptance.json', result)
    print(json.dumps(result.get('metrics', result)), flush=True)


if __name__ == '__main__':
    main()
