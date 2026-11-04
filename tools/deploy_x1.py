"""Stage and verify X1 files; publish atomically with the RF lock held.

No root privilege, bitstream download or RF initialization is performed.
Run only after audit_sentinel_v1b.ps1 passes. Existing v1 files are preserved;
the compatible Session factory change is backed up before replacement.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
BOARD_ROOT='/home/xilinx/sentinel'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def board_identity():
    facts={}
    for line in (ROOT/'docs/board_info.md').read_text(encoding='utf-8').splitlines():
        if re.fullmatch('[a-z_]+=.*',line):
            key,value=line.split('=',1);facts[key]=value.strip()
    if not re.fullmatch('[a-z_][a-z0-9_-]*',facts['board_user']) or not re.fullmatch('[0-9.]+',facts['board_ip']):
        raise ValueError('Invalid board identity')
    return facts['board_user']+'@'+facts['board_ip']


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--attempt',type=int,choices=(1,2,3),required=True)
    args=p.parse_args()
    evidence=ROOT/('board/measurements/x1_deployment_r%d.json'%args.attempt)
    if evidence.exists():
        p.error('Preserve prior deployment evidence')
    bundle=ROOT/'board/overlay/sentinel_v1b'
    acceptance=json.loads((bundle/'acceptance.json').read_text())
    if acceptance.get('status')!='PASS' or acceptance.get('cfar_version')!=0x43460002:
        raise RuntimeError('X1 implementation acceptance is required')
    for suffix in ('bit','hwh','xsa'):
        path=bundle/('sentinel_v1b.'+suffix)
        if sha(path)!=acceptance['artifacts_sha256'].get(path.name):
            raise RuntimeError('Accepted artifact changed')
    paths=['src/ps/sentinel/v1b.py','src/ps/sentinel/app/monitor_x1.py','src/ps/sentinel/app/selftest_x1.py',
           'src/ps/sentinel/app/runtime_v1.py','src/ps/sentinel/drivers/cfar_x1.py',
           'src/ps/sentinel/drivers/regs/cfar_x1.py',
           'board/scripts/run_x1_monitor.py','board/scripts/run_x1_selftest.py','board/scripts/x1_postflight.py']
    paths += [path.relative_to(ROOT).as_posix() for path in bundle.iterdir() if path.is_file()]
    tag='x1_deployment_r%d'%args.attempt
    stage=BOARD_ROOT+'/setup/'+tag
    options=['-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8',
             '-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2']
    target=board_identity()
    def ssh(command,stdin=None):
        completed=subprocess.run(['ssh',*options,target,command],input=stdin,text=True,
                                 capture_output=True,timeout=90)
        if completed.returncode:
            raise RuntimeError('SSH failed: '+completed.stderr[-1500:])
        return completed.stdout
    # Exclusive new staging directory prevents inadvertent evidence replacement.
    ssh('mkdir '+stage)
    manifest=[]
    for index,name in enumerate(paths):
        source=ROOT/name
        destination=name.removeprefix('src/') if name.startswith('src/ps/') else name.removeprefix('board/')
        staged='%03d_%s'%(index,source.name)
        subprocess.run(['scp',*options,'-p',str(source),target+':'+stage+'/'+staged],check=True,timeout=90)
        entry={'local':name,'destination':destination,'staged':staged,'sha256':sha(source)}
        if name=='src/ps/sentinel/app/runtime_v1.py':
            baseline=subprocess.check_output(['git','show','HEAD:'+name],cwd=ROOT)
            entry['expected_previous_sha256']=hashlib.sha256(baseline).hexdigest()
        manifest.append(entry)
    payload={'root':BOARD_ROOT,'stage':stage,'files':manifest}
    # Passed as Python data over SSH stdin, never interpolated as shell code.
    script='''import fcntl,hashlib,json,os,pathlib,shutil,sys
payload=json.loads(sys.stdin.readline())
root=pathlib.Path(payload['root']);stage=pathlib.Path(payload['stage'])
with open('/run/lock/zss_ad9361.lock','r') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 prepared=[]
 for item in payload['files']:
  src=stage/item['staged'];dest=root/item['destination']
  if root not in dest.resolve().parents:raise RuntimeError('Invalid destination')
  if hashlib.sha256(src.read_bytes()).hexdigest()!=item['sha256']:raise RuntimeError('Staged hash mismatch')
  if src.suffix=='.py':compile(src.read_bytes(),str(src),'exec')
  prepared.append((item,src,dest))
 # Validate the existing common module before replacement; preserve its bytes.
 for item,src,dest in prepared:
  if dest.exists():
   old=hashlib.sha256(dest.read_bytes()).hexdigest()
   item['previous_sha256']=old
   if old!=item['sha256']:
    if old!=item.get('expected_previous_sha256'):raise RuntimeError('Unexpected existing file: '+str(dest))
    backup=stage/('previous_'+old+'_'+dest.name)
    if not backup.exists():shutil.copyfile(str(dest),str(backup))
 for item,src,dest in prepared:
  dest.parent.mkdir(parents=True,exist_ok=True)
  temporary=dest.with_name(dest.name+'.'+stage.name+'.tmp')
  with temporary.open('xb') as out:
   out.write(src.read_bytes());out.flush();os.fsync(out.fileno())
  os.replace(str(temporary),str(dest));os.utime(str(dest),(src.stat().st_atime,src.stat().st_mtime))
  fd=os.open(str(dest.parent),os.O_RDONLY|os.O_DIRECTORY)
  try:os.fsync(fd)
  finally:os.close(fd)
 for item,src,dest in prepared:
  if hashlib.sha256(dest.read_bytes()).hexdigest()!=item['sha256']:raise RuntimeError('Published hash mismatch')
 print(json.dumps({'status':'PASS','files':payload['files'],'boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'hardware_accessed':False}))
'''
    # The first Python reads a JSON line, then execs the fixed installer source.
    command="python3 -c 'import sys; s=sys.stdin.readline(); exec(s)'"
    bootstrap='import io,sys; payload='+repr(json.dumps(payload))+'; sys.stdin=io.StringIO(payload); exec('+repr(script)+')'
    result=json.loads(ssh(command,bootstrap+chr(10)))
    result.update(recorded_at_pc=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
                  scope='File-only X1 deployment with SHA256 and RF ownership lock; no overlay loading or RF',
                  staging_directory=stage)
    evidence.write_text(json.dumps(result,indent=2)+chr(10),encoding='utf-8')
    Path(str(evidence)+'.sha256').write_text(sha(evidence)+'  '+evidence.name+chr(10),encoding='ascii')
    print('X1_DEPLOYMENT_PASS files='+str(len(manifest)))


if __name__=='__main__':
    main()
