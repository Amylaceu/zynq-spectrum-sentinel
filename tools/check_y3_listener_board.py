"""Check integrated listener on board Python with fake I/O; never access PL/RF.

Transfers only Python sources to a new unprivileged directory, verifies hashes,
then exercises normal playback and a final-interval fault with injected objects.
This is runtime compatibility evidence, not a speaker or FPGA acceptance.
"""
import argparse
import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import tarfile

from x2_transport import ROOT, REMOTE, PYTHON, Transport, sha, write_evidence


INSTALL_PYTHON = r'''import hashlib,json,pathlib,sys,tarfile
p=json.load(sys.stdin);root=pathlib.Path(p['root']);archive=pathlib.Path(p['archive'])
if hashlib.sha256(archive.read_bytes()).hexdigest()!=p['archive_sha256']:raise ValueError('Archive digest')
# Python-only compatibility check: no shared hardware lock, overlay or library.
root.mkdir(exist_ok=False)
with tarfile.open(str(archive)) as tar:
 entries=tar.getmembers()
 if sorted(m.name for m in entries)!=sorted(p['files']):raise ValueError('Unexpected members')
 for member in entries:
  relative=pathlib.PurePosixPath(member.name)
  if not member.isfile() or relative.is_absolute() or '..' in relative.parts or relative.suffix!='.py':raise ValueError('Non-Python or unsafe member')
  data=tar.extractfile(member).read()
  if hashlib.sha256(data).hexdigest()!=p['files'][member.name]:raise ValueError('Payload digest')
  compile(data,member.name,'exec')
  destination=root/member.name;destination.parent.mkdir(parents=True,exist_ok=True)
  with destination.open('xb') as stream:stream.write(data)
print('PYTHON_ONLY_INSTALL_PASS')
'''


CHECK = r'''import hashlib,json,pathlib,sys
from types import SimpleNamespace
p=json.load(sys.stdin);root=pathlib.Path(p['root'])
for name,digest in p['files'].items():
 if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise ValueError('Payload changed: '+name)
sys.path.insert(0,str(root/'ps'))
from sentinel.listen_y3 import FMListener,validate_listen
from sentinel.capture_x5 import select_channel
from sentinel.app import monitor_x5
validate_listen('sentinel_v2_100m',95800000,96400000,-21)
cases=[]
for inject in (False,True):
 events=[];now=[0.0];evidence={}
 state=dict(playing=True,enabled=True,fifo_level=4096,frames=0,pcm_samples=0,iq_overflow=False,pcm_full=False,underflows=0)
 audio=SimpleNamespace(disable=lambda release_pins:events.append('pins_off'),start=lambda:None,
   configure=lambda station,lo,codec:select_channel(station-lo),snapshot=lambda:dict(state))
 codec=SimpleNamespace(initialize=lambda volume_db:None,unmute=lambda:events.append('unmute'),shutdown=lambda:events.append('mute') or [])
 hw=SimpleNamespace(audio=audio,channel_health=lambda:0,x5_status=SimpleNamespace(read=lambda offset:0))
 def advance(seconds):now[0]+=seconds
 listener=FMListener(hw,95800000,96400000,evidence,codec=codec,clock=lambda:now[0],sleep=advance)
 caught=False
 try:
  with listener:
   listener.wait_ready(lambda:None)
   now[0]+=1;state.update(frames=48000,pcm_samples=48000)
   sample=listener.sample()
   assert abs(sample['audio_frame_rate_hz']-48000)<1e-6
   if inject:state['underflows']=1
 except RuntimeError:
  if not inject:raise
  caught=True
 assert caught==inject
 assert events[-2:]==['mute','pins_off']
 assert evidence['status']==('failed' if inject else 'stopped_awaiting_human')
 cases.append(dict(injected_underflow=inject,evidence=evidence))
assert not any(name=='pynq' or name.startswith('pynq.') for name in sys.modules)
print(json.dumps(dict(status='PASS_BOARD_PYTHON_FAKE_IO',python=sys.version,
 boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),cases=cases,
 hardware_accessed=False,rf_initialized=False,speaker_played=False)))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    args = parser.parse_args()
    tag = 'y3_listener_python_r%d' % args.attempt
    receipt = ROOT/'board/measurements'/(tag+'.json')
    archive = ROOT/'build'/(tag+'_runtime.tar.gz')
    if receipt.exists() or archive.exists():
        raise FileExistsError('Preserve previous board Python check')
    files = {}
    for path in sorted((ROOT/'src/ps/sentinel').rglob('*.py')):
        ast.parse(path.read_text(encoding='utf-8'), feature_version=(3, 8))
        files[path.relative_to(ROOT/'src').as_posix()] = path
    manifest = {name: sha(path) for name, path in files.items()}
    with tarfile.open(archive, 'x:gz') as package:
        for name, path in files.items():
            package.add(path, arcname=name, recursive=False)
    record = dict(status='STARTED', recorded_utc=datetime.now(timezone.utc).isoformat(),
                  source_sha256=manifest, archive_sha256=sha(archive),
                  runner_sha256=sha(Path(__file__)), hardware_tested=False)
    try:
        transport = Transport()
        stage = REMOTE+'/setup/'+tag
        transport.ssh(['test', '!', '-e', stage])
        transport.ssh(['test', '!', '-e', stage+'.tar.gz'])
        transport.copy(archive, transport.target+':'+stage+'.tar.gz')
        transport.ssh([PYTHON, '-I', '-c', INSTALL_PYTHON], payload=json.dumps(dict(
            root=stage, archive=stage+'.tar.gz', archive_sha256=sha(archive), files=manifest)))
        record['board'] = json.loads(transport.ssh([PYTHON, '-I', '-c', CHECK],
            payload=json.dumps(dict(root=stage, files=manifest))))
        record['status'] = record['board']['status']
    except Exception as error:
        record.update(status='FAIL', error=repr(error))
        raise
    finally:
        write_evidence(receipt, record)
    print(json.dumps(dict(status=record['status'], receipt=str(receipt),
                         python=record['board']['python'], hardware_tested=False), indent=2))


if __name__ == '__main__':
    main()
