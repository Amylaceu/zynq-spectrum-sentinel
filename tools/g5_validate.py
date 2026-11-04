"""Bounded show rehearsal. Antenna consent is explicit, credentials stdin only."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'src/ps')]
from x2_transport import Transport, REMOTE, PYTHON
from g3_validate import completed
from fetch_release_evidence import fetch
from run_x1_board import write_evidence, sha
from g1_evaluate import evaluate


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--group', choices=('A', 'B'), required=True)
    p.add_argument('--attempt', type=int, choices=(1, 2, 3), default=1)
    p.add_argument('--configuration-a-confirmed', action='store_true')
    p.add_argument('--antenna-b-direct-confirmed', action='store_true')
    p.add_argument('--sudo-stdin', action='store_true', required=True)
    args = p.parse_args()
    if not (args.configuration_a_confirmed if args.group=='A' else args.antenna_b_direct_confirmed):
        p.error('Confirm the actual antenna configuration before RF operation')
    t = Transport(password=sys.stdin.readline().rstrip('\r\n'))
    if not t.password:
        p.error('Missing credential on stdin')
    root = REMOTE+'/release/v2'
    name = 'g5_'+args.group.lower()+'_board_r%d' % args.attempt
    output = ROOT/'board/measurements'/name
    output.mkdir(exist_ok=False)
    child = None
    result = dict(status='STARTED', group=args.group, cycles=3,
        configuration='A' if args.group=='A' else 'B-direct confirmed',
        host_started_utc=datetime.now(timezone.utc).isoformat(), pl_rebuilt=False)
    try:
        command = ['sh', root+'/scripts/sentinel.sh', 'show', args.group, '--cycles', '3']
        if args.group=='B':
            command += ['--antenna-confirmed', 'yes']
        script = '''import pathlib,json,subprocess,sys,fcntl
p=json.loads(sys.argv[1]);root=pathlib.Path(p['root'])
if pathlib.Path('/run/zss_release_v2.json').exists():raise RuntimeError('Existing supervisor')
with open('/run/lock/zss_ad9361.lock','a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
check=subprocess.run([sys.executable,'-I',str(root/'scripts/y3_postflight.py'),'--bit',str(root/'overlay/sentinel_v2_100m/sentinel_v2_100m.bit')],capture_output=True,text=True)
if check.returncode:raise RuntimeError(check.stderr[-1000:])
value=json.loads(check.stdout)
if value.get('status')!='PASS' or any(value.get(k)!=0 for k in ('gpio_data','source_ctrl','audio_control')):raise RuntimeError('Not stopped')
with open(p['log'],'x') as log:
 child=subprocess.Popen(p['command'],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps(dict(pid=child.pid,boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),preflight=value)))
'''
        value = t.ssh([PYTHON, '-I', '-c', script, json.dumps(dict(root=root,
            log=root+'/logs/'+name+'.log',command=command))], privileged=True)
        result['launch'] = json.loads(value)
        write_evidence(output/'launch.json', result['launch'])
        print('G5_STARTED', name, flush=True)
        env = dict(os.environ)
        env.pop('QT_QPA_PLATFORM', None)
        with (output/'gui.log').open('x', encoding='utf-8') as log:
            child = subprocess.Popen([sys.executable, str(ROOT/'tools/host/g5_live_probe.py'),
                '--address', t.target.rsplit('@',1)[-1], '--group', args.group,
                '--output', str(output)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            tag = completed(t, name, 660)
            result['tag'] = tag
            write_evidence(output/'board_finished.json', dict(tag=tag, host_utc=datetime.now(timezone.utc).isoformat()))
            child.wait(timeout=30)
        if child.returncode:
            raise RuntimeError('GUI failed; see gui.log')
        fetch(tag, 'show', output/'board_raw')
        raw = output/'board_raw/measurements'/('show_'+tag)
        result['demo'] = json.loads((raw/'demo.json').read_text())
        if args.group=='A':
            result['demo_evaluation'] = evaluate(raw)
        result['gui'] = json.loads((output/'gui_metrics.json').read_text(encoding='utf-8'))
        result['status'] = 'MEASURED'
    except BaseException as error:
        result.update(status='FAIL', error=repr(error))
        raise
    finally:
        if child is not None and child.poll() is None:
            write_evidence(output/'board_finished.json', dict(status='ABORTED'))
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.terminate()
                child.wait(timeout=10)
        try:
            result['stop'] = t.ssh(['sh',root+'/scripts/sentinel.sh','stop'],privileged=True)
            result['postflight'] = json.loads(t.ssh([PYTHON,'-I',root+'/scripts/y3_postflight.py',
                '--bit',root+'/overlay/sentinel_v2_100m/sentinel_v2_100m.bit'],privileged=True))
        except BaseException as error:
            result.update(status='FAIL', cleanup_error=repr(error))
        result['files_sha256'] = {f.relative_to(output).as_posix():sha(f)
                                 for f in output.rglob('*') if f.is_file()}
        write_evidence(output/'validation.json', result)
    print('G5_MEASUREMENT_COMPLETE', result['status'], flush=True)


if __name__ == '__main__':
    main()
