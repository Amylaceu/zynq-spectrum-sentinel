"""Deploy independent X2 files after audit; retain all accepted predecessors."""
import argparse
from datetime import datetime, timezone
import json

from x2_transport import (ROOT, REMOTE, Transport, remote_name, sha, verified, write_evidence)

NEW = ('src/ps/sentinel/v1c.py', 'src/ps/sentinel/drivers/stream_x2.py',
       'src/ps/sentinel/regs/__init__.py', 'src/ps/sentinel/regs/stream_x2.py',
       'src/ps/sentinel/rf/ad9361_x2.py', 'src/ps/sentinel/app/runtime_x2.py',
       'src/ps/sentinel/app/monitor_x2.py', 'src/ps/sentinel/app/selftest_x2.py',
       'src/ps/libad9361_pynq/Makefile.x2', 'src/ps/libad9361_pynq/app/x2_api_c.c',
       'board/scripts/run_x2_monitor.py', 'board/scripts/run_x2_selftest.py',
       'board/scripts/x2_postflight.py')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    args = parser.parse_args()
    output = ROOT/('board/measurements/x2_deployment_r%d.json' % args.attempt)
    if output.exists() or output.with_suffix('.json.sha256').exists():
        raise FileExistsError(output)
    software_path = ROOT/('docs/x2_software_predeployment_r%d.json' % args.attempt)
    software = verified(software_path)
    if software['status'] != 'READY_FOR_DEPLOYMENT':
        raise ValueError('Software freeze must pass')
    for name, digest in software['source_sha256'].items():
        if sha(ROOT/name) != digest:
            raise ValueError('Frozen software changed: '+name)
    bundle = ROOT/'board/overlay/sentinel_v1c'
    acceptance = verified(bundle/'acceptance.json')
    if acceptance['status'] != 'PASS' or acceptance['stream_version'] != 0x58320001:
        raise ValueError('Routed X2 acceptance required')
    for name, digest in acceptance['artifacts_sha256'].items():
        if sha(bundle/name) != digest:
            raise ValueError('Artifact differs from audit: '+name)
    frozen = verified(ROOT/'docs/x1_software_predeployment_r3.json')
    for name, digest in frozen['source_sha256'].items():
        if sha(ROOT/name) != digest:
            raise ValueError('Frozen X1 file changed: '+name)
    # Common local modules must be the exact files already deployed. Only new
    # X2 files may be created; no library/module used by N4 or X1 is replaced.
    common = {p.relative_to(ROOT).as_posix(): sha(p)
              for p in (ROOT/'src/ps/sentinel').rglob('*.py')
              if p.relative_to(ROOT).as_posix() not in NEW}
    # Verify shared C inputs used to build the separate library as well.
    for pattern in ('app/*.c', 'app/*.h', 'platform/*.c', 'platform/*.h'):
        for path in (ROOT/'src/ps/libad9361_pynq').glob(pattern):
            name = path.relative_to(ROOT).as_posix()
            if name not in NEW:
                common[name] = sha(path)
    common['src/ps/libad9361_pynq/Makefile'] = sha(ROOT/'src/ps/libad9361_pynq/Makefile')
    transport = Transport()
    # Missing unrelated modules are not needed for X2; require every existing
    # shared board module to match and record which were present.
    script = """import hashlib,json,pathlib,sys
p=json.load(sys.stdin);root=pathlib.Path(p['root']);present={};missing=[]
for name,digest in p['files'].items():
 path=root/name
 if not path.exists():missing.append(name);continue
 if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise RuntimeError('Shared source mismatch: '+name)
 present[name]=digest
print(json.dumps(dict(present=present,missing=missing)))
"""
    shared = json.loads(transport.ssh(['python3', '-c', script], payload=json.dumps(
        dict(root=REMOTE, files={remote_name(n): h for n, h in common.items()}))))
    required = ('ps/sentinel/v1.py', 'ps/sentinel/v1b.py', 'ps/sentinel/app/runtime_v1.py',
                'ps/sentinel/app/selftest_v1.py', 'ps/sentinel/app/monitor_x1.py',
                'ps/sentinel/app/monitor_x1_guard8.py', 'ps/libad9361_pynq/Makefile')
    if any(name not in shared['present'] for name in required):
        raise ValueError('Required accepted dependency absent')
    files = list(NEW)+[p.relative_to(ROOT).as_posix() for p in bundle.iterdir() if p.is_file()]
    tag = 'x2_deployment_r%d' % args.attempt
    stage = REMOTE+'/setup/'+tag
    transport.ssh(['mkdir', stage])
    entries = []
    for index, name in enumerate(files):
        path = ROOT/name
        staged = '%03d_%s' % (index, path.name)
        transport.copy(path, transport.target+':'+stage+'/'+staged)
        entries.append(dict(local=name, destination=remote_name(name), staged=staged, sha256=sha(path)))
    installer = """import fcntl,hashlib,json,os,pathlib,sys
p=json.load(sys.stdin);root=pathlib.Path(p['root']);stage=pathlib.Path(p['stage'])
with open('/run/lock/zss_ad9361.lock','r') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 for item in p['files']:
  src=stage/item['staged'];dst=root/item['destination']
  if root not in dst.resolve().parents:raise RuntimeError('Invalid destination')
  if hashlib.sha256(src.read_bytes()).hexdigest()!=item['sha256']:raise RuntimeError('Staged digest mismatch')
  if dst.exists() and hashlib.sha256(dst.read_bytes()).hexdigest()!=item['sha256']:raise RuntimeError('Refuse overwrite')
  if dst.suffix=='.py':compile(src.read_bytes(),str(dst),'exec')
 for item in p['files']:
  dst=root/item['destination'];dst.parent.mkdir(parents=True,exist_ok=True)
  if dst.exists():continue
  tmp=dst.with_name(dst.name+'.'+stage.name+'.tmp')
  with tmp.open('xb') as out:
   out.write((stage/item['staged']).read_bytes());out.flush();os.fsync(out.fileno())
  os.replace(str(tmp),str(dst))
  fd=os.open(str(dst.parent),os.O_RDONLY|os.O_DIRECTORY)
  try:os.fsync(fd)
  finally:os.close(fd)
 for item in p['files']:
  if hashlib.sha256((root/item['destination']).read_bytes()).hexdigest()!=item['sha256']:raise RuntimeError('Published digest mismatch')
 print(json.dumps(dict(status='PASS',files=p['files'],hardware_accessed=False)))
"""
    deployed = json.loads(transport.ssh(['python3', '-c', installer], payload=json.dumps(
        dict(root=REMOTE, stage=stage, files=entries))))
    # Import the actual board modules with its Python 3.8 interpreter before any
    # hardware access; this catches missing transitive shared dependencies.
    imports = "import sys;sys.path.insert(0,%r);import sentinel.app.monitor_x2;import sentinel.app.selftest_x2;print('X2_IMPORTS_PASS')" % (REMOTE+'/ps')
    import_result = transport.ssh(['/usr/local/share/pynq-venv/bin/python3', '-I', '-c', imports]).strip()
    if import_result != 'X2_IMPORTS_PASS':
        raise RuntimeError('Board X2 import check failed')
    write_evidence(output, dict(status='PASS_DEPLOYMENT', recorded_at_pc=datetime.now(timezone.utc).isoformat(),
        deployment=deployed, shared_sources=shared,
        board_import_check=import_result,
        software_manifest_sha256=sha(software_path),
        implementation_acceptance_sha256=sha(bundle/'acceptance.json'),
        source_sha256={name: sha(ROOT/name) for name in NEW},
        deployment_tool_sha256=sha(ROOT/'tools/deploy_x2.py')))
    print('X2_DEPLOYMENT_PASS files='+str(len(entries)))


if __name__ == '__main__':
    main()
