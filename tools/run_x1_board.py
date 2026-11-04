"""Run one explicitly confirmed X1 board step; preserve result and exit evidence.

The caller confirms configuration A for this step. Optional --sudo-stdin reads
one password line without echo or saving it. Otherwise sudo must be noninteractive.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
from zoneinfo import ZoneInfo

from deploy_x1 import board_identity

ROOT=(Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False)
      else Path(__file__).resolve().parents[1])
REMOTE='/home/xilinx/sentinel'
PYTHON='/usr/local/share/pynq-venv/bin/python3'
OPTIONS=['-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8',
         '-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_evidence(path,record):
    if path.exists() or Path(str(path)+'.sha256').exists():
        raise FileExistsError('Preserve evidence: '+str(path))
    path.write_text(json.dumps(record,indent=2)+chr(10),encoding='utf-8')
    Path(str(path)+'.sha256').write_text(sha(path)+'  '+path.name+chr(10),encoding='ascii')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('selftest','capacity','station'),required=True)
    p.add_argument('--attempt',type=int,choices=(1,2,3),required=True)
    p.add_argument('--confirm-configuration-a',action='store_true',required=True)
    p.add_argument('--sudo-stdin',action='store_true')
    p.add_argument('--average-shift',type=int,default=3)
    p.add_argument('--min-width',type=int,default=2)
    p.add_argument('--merge-gap',type=int,default=6)
    p.add_argument('--alpha',type=int,default=1974)
    p.add_argument('--mask',action='append',default=[])
    args=p.parse_args()
    password=sys.stdin.readline().rstrip(chr(13)+chr(10)) if args.sudo_stdin else None
    if args.sudo_stdin and not password:
        p.error('Missing sudo credential on stdin')
    tag='x1_%s_r%d'%(args.mode,args.attempt)
    result_path=ROOT/'board/measurements'/(tag+'.json')
    receipt=ROOT/'board/measurements'/(tag+'_execution.json')
    log=ROOT/'logs'/('X1_'+args.mode+'_r%d.log'%args.attempt)
    if any(path.exists() for path in (result_path,receipt,log)):
        p.error('Preserve previous run; do not reuse a tag')
    target=board_identity()
    def ssh(command,timeout=30):
        r=subprocess.run(['ssh',*OPTIONS,target,command],capture_output=True,text=True,timeout=timeout)
        if r.returncode:
            raise RuntimeError('Read-only SSH check failed: '+r.stderr[-1000:])
        return r.stdout
    boot=ssh('cat /proc/sys/kernel/random/boot_id').strip()
    remote_result=REMOTE+'/measurements/'+tag+'.json'
    absent=ssh('test ! -e '+remote_result+' && echo NEW_OUTPUT')
    if absent.strip()!='NEW_OUTPUT':
        raise RuntimeError('Remote result already exists')
    script='run_x1_selftest.py' if args.mode=='selftest' else 'run_x1_monitor.py'
    command=[PYTHON,'-I',REMOTE+'/scripts/'+script,'--bit',REMOTE+'/overlay/sentinel_v1b/sentinel_v1b.bit',
             '--out',remote_result]
    if args.mode=='selftest':
        command+=['--references',REMOTE+'/data/reference/spectrum']
    else:
        command+=['--lo',str(98000000 if args.mode=='capacity' else 96400000),
                  '--seconds','120','--average-shift',str(args.average_shift),'--min-width',str(args.min_width),
                  '--merge-gap',str(args.merge_gap),'--alpha',str(args.alpha),'--capture-power']
        for mask in args.mask:
            command+=['--mask',mask]
    sudo=['sudo','-S','-p',''] if args.sudo_stdin else ['sudo','-n']
    started=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
    with log.open('xb') as stream:
        process=subprocess.Popen(['ssh',*OPTIONS,target,shlex.join(sudo+command)],stdin=subprocess.PIPE,
                                 stdout=stream,stderr=subprocess.STDOUT)
        process.communicate((password+chr(10)).encode() if password is not None else b'')
    password=None
    record={'started_at_pc':started,'ended_at_pc':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
            'command':command,'ssh_exit_code':process.returncode,'boot_id_before':boot,
            'configuration_a_confirmed':True,'log':log.relative_to(ROOT).as_posix(),'log_sha256':sha(log),
            'scope':'Command exit/result retrieval only; metrics and visual acceptance separate'}
    try:
        record['boot_id_after']=ssh('cat /proc/sys/kernel/random/boot_id').strip()
        subprocess.run(['scp',*OPTIONS,target+':'+remote_result,str(result_path)],check=True,timeout=30)
        record['result_sha256']=sha(result_path)
        Path(str(result_path)+'.sha256').write_text(sha(result_path)+'  '+result_path.name+chr(10),encoding='ascii')
        measurement=json.loads(result_path.read_text(encoding='utf-8'))
        record['result_status']=measurement.get('status')
        if args.mode=='selftest' and measurement.get('raw_archive_sha256'):
            archive=result_path.with_suffix('.npz')
            subprocess.run(['scp',*OPTIONS,target+':'+remote_result.removesuffix('.json')+'.npz',str(archive)],check=True,timeout=30)
            if sha(archive)!=measurement['raw_archive_sha256']:
                raise RuntimeError('Self-test NPZ hash mismatch')
            record['archive_sha256']=sha(archive)
        record['status']='PASS_EXECUTION' if process.returncode==0 and record['boot_id_after']==boot and record['result_status'] in ('passed','completed') else 'FAIL_EXECUTION'
    except Exception as error:
        record.update(status='FAIL_RESULT_RETRIEVAL',error=str(error))
    write_evidence(receipt,record)
    print(json.dumps(record,indent=2),flush=True)
    return 0 if record['status']=='PASS_EXECUTION' else 1


if __name__=='__main__':
    raise SystemExit(main())
