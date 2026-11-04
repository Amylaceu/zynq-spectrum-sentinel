"""Launch one authorized B-direct demo attempt with durable launch evidence."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from x2_transport import ROOT, REMOTE, PYTHON, Transport, write_evidence


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--attempt', type=int, choices=(1,2,3), required=True)
    p.add_argument('--antenna-b-direct-confirmed', action='store_true', required=True)
    p.add_argument('--sudo-stdin', action='store_true')
    args=p.parse_args()
    evidence=ROOT/'board/measurements'/('f3_demo_r%d_start.json'%args.attempt)
    if evidence.exists():raise FileExistsError('Preserve previous launch')
    password=sys.stdin.readline().rstrip('\r\n') if args.sudo_stdin else None
    if args.sudo_stdin and not password:p.error('Missing sudo credential')
    root=REMOTE+'/release/v2'
    script='''import sys,pathlib,json,subprocess,fcntl
root=pathlib.Path(sys.argv[1]);attempt=int(sys.argv[2])
sys.path.insert(0,str(root/'ps'))
from sentinel.release_support import verify_release
m=verify_release(root)
if pathlib.Path('/run/zss_release_v2.json').exists():raise RuntimeError('Existing supervisor state')
check=subprocess.run([sys.executable,'-I',str(root/'scripts/y3_postflight.py'),'--bit',str(root/'overlay/sentinel_v2_100m/sentinel_v2_100m.bit')],capture_output=True,text=True)
if check.returncode:raise RuntimeError('Stopped-state preflight failed: '+check.stderr[-1000:])
preflight=json.loads(check.stdout)
if preflight.get('status')!='PASS' or any(preflight[k]!=0 for k in ('gpio_data','source_ctrl','audio_control')):raise RuntimeError('Hardware not fully stopped')
with open('/run/lock/zss_release_v2.lock','a') as outer,open('/run/lock/zss_ad9361.lock','a') as rf:
 for lock in (outer,rf):fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
# The supervisor takes both execution ownership and hardware checks itself.
log=root/'logs'/('F3_demo_r%d_supervisor.log'%attempt)
with log.open('x') as out:
 process=subprocess.Popen([sys.executable,'-I',str(root/'scripts/release_entry.py'),'demo','B','--antenna-confirmed','yes','--cycles','3'],stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps({'pid':process.pid,'supervisor_log':str(log),'manifest_files':len(m['files']),'boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()}))
'''
    t=Transport(password=password)
    result=json.loads(t.ssh([PYTHON,'-I','-c',script,root,str(args.attempt)],privileged=True,timeout=30))
    record=dict(result,status='STARTED',group='B',cycles=3,host_utc=datetime.now(timezone.utc).isoformat(),
        antenna='B-direct confirmed TX1A/RX1A',frequency_hz=2450000000,attenuation_floor_db=40)
    write_evidence(evidence,record)
    print(json.dumps(record))


if __name__=='__main__':
    main()
