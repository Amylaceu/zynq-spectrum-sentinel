"""Bounded raw-DMA diagnostic; credentials only on stdin; immutable evidence."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'src/ps')]
from x2_transport import Transport,REMOTE,PYTHON,OPTIONS
from run_x1_board import sha,write_evidence


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sudo-stdin',required=True,action='store_true')
    p.add_argument('--seconds',type=int,choices=(10,600),required=True)
    p.add_argument('--attempt',type=int,choices=(1,2,3),default=1)
    a=p.parse_args()
    t=Transport(password=sys.stdin.readline().rstrip('\r\n'))
    name='g4d_dma_r%d'%a.attempt
    output=ROOT/'board/measurements'/name
    output.mkdir(exist_ok=False)
    root=REMOTE+'/release/v2'
    source=ROOT/'board/scripts/g4d_dma_audit.py'
    script=REMOTE+'/setup/g4d_dma_'+sha(source)+'.py'
    t.copy(source,t.target+':'+script)
    if t.ssh(['sha256sum',script]).split()[0]!=sha(source):
        raise ValueError('Diagnostic script checksum mismatch')
    directory=root+'/measurements/'+name
    log=root+'/logs/'+name+'.log'
    wrapper='''import json,pathlib,subprocess,signal
p=json.loads(%r)
if pathlib.Path('/run/zss_release_v2.json').exists():raise RuntimeError('Release running')
with open(p['log'],'x') as stream:
 child=subprocess.Popen(p['command'],stdout=stream,stderr=subprocess.STDOUT)
 try:code=child.wait(timeout=p['timeout'])
 except subprocess.TimeoutExpired:
  child.send_signal(signal.SIGTERM)
  try:child.wait(timeout=15)
  except subprocess.TimeoutExpired:raise RuntimeError('DMA cleanup not confirmed; do not access hardware')
  raise RuntimeError('Diagnostic bounded timeout')
print(json.dumps(dict(exit_code=code,pid=child.pid)))
'''%json.dumps(dict(log=log,command=[PYTHON,script,'--root',root,'--seconds',str(a.seconds),
                                   '--out',directory],timeout=a.seconds+90))
    result=dict(host_started_utc=datetime.now(timezone.utc).isoformat(),configuration='A',
                tx_requested=False,script_sha256=sha(source),seconds=a.seconds)
    try:
        result['execution']=json.loads(t.ssh([PYTHON,'-c',wrapper],privileged=True,timeout=a.seconds+120))
        hashes=json.loads(t.ssh(['python3','-c',
            'import pathlib,hashlib,json; p=pathlib.Path('+repr(directory)+'); print(json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in p.iterdir() if f.is_file()}))']))
        subprocess.run(['scp',*OPTIONS,'-r',t.target+':'+directory,str(output/'raw')],check=True,timeout=60)
        for path in (output/'raw').iterdir():
            if sha(path)!=hashes[path.name]:raise ValueError('Downloaded DMA evidence differs')
        t.copy(t.target+':'+log,output/'board.log')
        result['measurement']=json.loads((output/'raw/result.json').read_text(encoding='utf-8'))
        result['files_sha256']=hashes
        result['postflight']=json.loads(t.ssh([PYTHON,'-I',root+'/scripts/y3_postflight.py',
            '--bit',root+'/overlay/sentinel_v2_100m/sentinel_v2_100m.bit'],privileged=True))
    except BaseException as error:
        result['error']=repr(error)
        raise
    finally:
        write_evidence(output/'validation.json',result)
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
