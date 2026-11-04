"""Stage two new X3 files, check imported dependencies, run a bounded board test.

PC Python 3.12; SSH host/user read from docs/board_info.md. Password, when
needed, is read from stdin and forwarded only to sudo's private stdin pipe.
Long execution must be launched in background; logs/X3_perf_rN.log is created.
"""
import argparse
import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import sys

from x2_transport import ROOT, REMOTE, PYTHON, OPTIONS, Transport, sha, write_evidence

NEW = ('src/ps/sentinel/app/perf_x3.py', 'board/scripts/run_x3_perf.py')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--confirm-configuration-a', action='store_true', required=True)
    parser.add_argument('--sudo-stdin', action='store_true')
    parser.add_argument('--section', choices=('all', 'receive'), default='all')
    args = parser.parse_args()
    password = sys.stdin.readline().rstrip('\r\n') if args.sudo_stdin else None
    if args.sudo_stdin and not password:
        parser.error('Missing sudo credential')
    transport = Transport(password)
    tag = ('x3_perf_r%d' if args.section == 'all' else 'x3_receive_r%d') % args.attempt
    output = ROOT/'board/measurements'/(tag+'.json')
    receipt = output.with_name(tag+'_execution.json')
    log = ROOT/'logs'/(tag.replace('x3_', 'X3_')+'.log')
    if any(p.exists() for p in (output, receipt, log)):
        raise FileExistsError('Preserve previous evidence')
    for name in NEW:
        ast.parse((ROOT/name).read_text(encoding='utf-8'), feature_version=(3, 8))
    acceptance_path = ROOT/'board/overlay/sentinel_v1b/acceptance.json'
    acceptance = json.loads(acceptance_path.read_text())
    if acceptance['status'] != 'PASS':
        raise ValueError('Audited v1b required')
    bundle_files = {'overlay/sentinel_v1b/'+name:digest for name, digest in acceptance['artifacts_sha256'].items()}
    bundle_files['overlay/sentinel_v1b/acceptance.json'] = sha(acceptance_path)
    transport.check_files(bundle_files)
    stage = REMOTE+'/setup/'+tag
    transport.ssh(['mkdir', stage])
    files = []
    for index, name in enumerate(NEW):
        source = ROOT/name
        destination = name[4:] if name.startswith('src/') else name[6:]
        staged = str(index)+'_'+source.name
        transport.copy(source, transport.target+':'+stage+'/'+staged)
        files.append(dict(local=name, destination=destination, staged=staged, sha256=sha(source)))
    installer = '''import fcntl,hashlib,json,os,pathlib,sys
p=json.load(sys.stdin);root=pathlib.Path(p['root']);stage=pathlib.Path(p['stage'])
with open('/run/lock/zss_ad9361.lock','r') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 for item in p['files']:
  src=stage/item['staged'];dst=root/item['destination']
  if root not in dst.resolve().parents:raise ValueError('Destination escape')
  if hashlib.sha256(src.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Stage digest')
  compile(src.read_bytes(),str(dst),'exec')
  if dst.exists():
   old=dst.read_bytes();item['previous_sha256']=hashlib.sha256(old).hexdigest()
   if old!=src.read_bytes():
    backup=stage/('previous_'+dst.name)
    with backup.open('xb') as out:out.write(old);out.flush();os.fsync(out.fileno())
 for item in p['files']:
  src=stage/item['staged'];dst=root/item['destination']
  tmp=stage/('publish_'+src.name)
  with tmp.open('xb') as out:out.write(src.read_bytes());out.flush();os.fsync(out.fileno())
  os.replace(str(tmp),str(dst))
  fd=os.open(str(dst.parent),os.O_RDONLY|os.O_DIRECTORY)
  try:os.fsync(fd)
  finally:os.close(fd)
  if hashlib.sha256(dst.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Publish digest')
print(json.dumps(p['files']))
'''
    deployment = json.loads(transport.ssh(['python3', '-c', installer], payload=json.dumps(
        dict(root=REMOTE, stage=stage, files=files))))
    imports = '''import sys,pathlib,hashlib,json
root=pathlib.Path(sys.argv[1]);sys.path.insert(0,str(root/'ps'))
import sentinel.app.perf_x3
files={}
for name,module in list(sys.modules.items()):
 if name=='sentinel' or name.startswith('sentinel.'):
  filename=getattr(module,'__file__',None)
  if filename is None:continue
  path=pathlib.Path(filename)
  files[path.relative_to(root).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
print(json.dumps(files))
'''
    dependencies = json.loads(transport.ssh([PYTHON, '-I', '-c', imports, REMOTE]))
    for name, digest in dependencies.items():
        if sha(ROOT/'src'/name) != digest:
            raise ValueError('Imported dependency differs from PC: '+name)
    dependencies['scripts/x1_postflight.py'] = sha(ROOT/'board/scripts/x1_postflight.py')
    transport.check_files(dependencies)
    def stopped():
        return json.loads(transport.ssh([PYTHON, '-I', REMOTE+'/scripts/x1_postflight.py'], privileged=True))
    preflight = stopped()
    boot = preflight['boot_id']
    if preflight['status'] != 'PASS':
        raise ValueError('Stopped state required')
    remote_output = REMOTE+'/measurements/'+output.name
    transport.ssh('test ! -e '+remote_output)
    library = REMOTE+'/ps/libad9361_pynq/libad9361_pynq.so'
    library_before = transport.ssh(['sha256sum', library]).split()[0]
    command = [PYTHON, '-I', REMOTE+'/scripts/run_x3_perf.py', '--bit',
               REMOTE+'/overlay/sentinel_v1b/sentinel_v1b.bit', '--out', remote_output,
               '--section', args.section]
    record = dict(started_at_pc=datetime.now(timezone.utc).isoformat(), configuration_a_confirmed=True,
        RF_TX_requested=False, deployment=deployment, imported_sources_sha256=dependencies,
        accepted_bundle_sha256=sha(acceptance_path), preflight=preflight, command=command,
        host_runner_sha256=sha(Path(__file__)), library_sha256_before=library_before)
    with log.open('xb') as stream:
        process = subprocess.run(['ssh', *OPTIONS, transport.target, shlex.join(transport.privileged(command))],
            input=(password+'\n').encode() if password else b'', stdout=stream,
            stderr=subprocess.STDOUT, timeout=240)
    record.update(ssh_exit_code=process.returncode, log_sha256=sha(log), log=log.relative_to(ROOT).as_posix())
    try:
        record['postflight'] = stopped()
        transport.copy(transport.target+':'+remote_output, str(output))
        record['measurement_sha256'] = sha(output)
        Path(str(output)+'.sha256').write_text(sha(output)+'  '+output.name+'\n', encoding='ascii')
        record['library_sha256_after'] = transport.ssh(['sha256sum', library]).split()[0]
        transport.check_files(dependencies)
        transport.check_files(bundle_files)
        measured = json.loads(output.read_text())
        passed = (process.returncode == 0 and measured['status'] == 'completed'
                  and record['postflight']['status'] == 'PASS' and record['postflight']['boot_id'] == boot
                  and measured['boot_id'] == boot and record['library_sha256_after'] == library_before)
        record['status'] = 'PASS_EXECUTION' if passed else 'FAIL_EXECUTION'
    except Exception as error:
        record.update(status='FAIL_RETRIEVAL_OR_POSTFLIGHT', error=str(error))
    record['ended_at_pc'] = datetime.now(timezone.utc).isoformat()
    record['scope'] = 'Execution only; PC analysis determines metrics independently'
    write_evidence(receipt, record)
    print(json.dumps(record, indent=2), flush=True)
    return 0 if record['status'] == 'PASS_EXECUTION' else 1


if __name__ == '__main__':
    raise SystemExit(main())
