"""Fetch a stopped release run and verify every copied file against remote SHA256.

Read-only SSH/scp; refuses a live supervisor and preserves existing directories.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from x2_transport import Transport, REMOTE, OPTIONS
from run_x1_board import write_evidence


def fetch(tag, kind, output, remote_root=None):
    if not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z_[a-f0-9]{8}', tag):
        raise ValueError('Require exact release run tag')
    if kind not in ('monitor', 'listen', 'selftest', 'demo', 'show'):
        raise ValueError('Unknown release run kind')
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    root = remote_root or REMOTE+'/release/v2'
    transport = Transport()
    script = '''import pathlib,json,hashlib,sys
p=json.load(sys.stdin);r=pathlib.Path(p['root']);tag=p['tag']
if pathlib.Path('/run/zss_release_v2.json').exists():raise RuntimeError('Release still running')
items=[r/'measurements'/(p['kind']+'_'+tag),r/'measurements'/(tag+'_execution.json'),r/'measurements'/(tag+'_execution.json.sha256'),r/'logs'/(tag+'.log')]
hashes={}
for item in items:
 if not item.exists():raise FileNotFoundError(str(item))
 for f in sorted(item.rglob('*')) if item.is_dir() else [item]:
  if f.is_symlink():raise RuntimeError('Unexpected symlink')
  if f.is_file():hashes[str(f.relative_to(r))]=hashlib.sha256(f.read_bytes()).hexdigest()
print(json.dumps(hashes))
'''
    hashes = json.loads(transport.ssh(['python3', '-c', script], payload=json.dumps(
        dict(root=root, tag=tag, kind=kind)), timeout=90))
    output.mkdir(parents=True)
    (output/'measurements').mkdir()
    (output/'logs').mkdir()
    source = '%s:%s/measurements/%s_%s' % (transport.target, root, kind, tag)
    subprocess.run(['scp', *OPTIONS, '-r', source, str(output/'measurements')],
                   check=True, timeout=180)
    for name in ('measurements/'+tag+'_execution.json',
                 'measurements/'+tag+'_execution.json.sha256', 'logs/'+tag+'.log'):
        transport.copy(transport.target+':'+root+'/'+name, output/name)
    actual = {}
    for path in output.rglob('*'):
        if path.is_file():
            name = path.relative_to(output).as_posix()
            actual[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != hashes:
        raise ValueError('Remote/local evidence set or checksum mismatch')
    write_evidence(output/'verification.json', dict(status='PASS', root=root,
        tag=tag, kind=kind, file_count=len(actual), files_sha256=actual))
    return output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tag', required=True)
    p.add_argument('--kind', choices=('monitor', 'listen', 'selftest', 'demo', 'show'), required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--remote-root')
    args = p.parse_args()
    print(fetch(args.tag, args.kind, args.output, args.remote_root))


if __name__ == '__main__':
    main()
