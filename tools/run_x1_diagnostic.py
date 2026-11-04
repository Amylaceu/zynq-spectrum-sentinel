"""Deploy or run bounded X1 diagnostics without changing frozen input files.

Credentials enter through stdin. Test mode holds RF in reset. RF mode requires
the user's confirmed RX1A antenna and empty TX connection. Runs are write-once.
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
from run_x1_board import OPTIONS, PYTHON, REMOTE, ROOT, sha, write_evidence

NEW_FILES = ('src/ps/sentinel/app/diagnose_x1.py', 'board/scripts/run_x1_diagnostic.py')


def destination(relative):
    if relative.startswith('src/ps/'):
        return relative[4:]
    if relative.startswith('board/scripts/'):
        return relative[6:]
    raise ValueError('Not a deployable board source')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('deploy', 'test', 'rf'), required=True)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--frames', type=int, default=96)
    parser.add_argument('--confirm-rx1a-tx-empty', action='store_true')
    parser.add_argument('--sudo-stdin', action='store_true')
    parser.add_argument('--replace-from-deployment', type=Path,
                        help='Previous diagnostic deployment receipt authorizing an exact-hash replacement')
    args = parser.parse_args()
    if args.mode == 'rf' and not args.confirm_rx1a_tx_empty:
        parser.error('RF requires an explicit user connection confirmation')
    if not 4 <= args.frames <= 128:
        parser.error('Expected 4..128 frames')
    tag = 'x1_diagnostic_%s_r%d' % (args.mode, args.attempt)
    output = ROOT / ('board/measurements/' + tag + '.json')
    receipt = output.with_name(tag + '_execution.json')
    log = ROOT / ('logs/X1_diagnostic_%s_r%d.log' % (args.mode, args.attempt))
    for path in (output, output.with_suffix('.npz'), receipt, log):
        if path.exists() or Path(str(path) + '.sha256').exists():
            parser.error('Preserve prior experiment: ' + str(path))
    frozen = json.loads((ROOT / 'docs/x1_software_predeployment_r3.json').read_text())
    for relative, digest in frozen['source_sha256'].items():
        if sha(ROOT / relative) != digest:
            raise RuntimeError('Frozen local input changed: ' + relative)
    password = sys.stdin.readline().rstrip('\r\n') if args.sudo_stdin else None
    if args.sudo_stdin and not password:
        parser.error('Missing sudo credential on stdin')
    target = board_identity()
    prefix = ['sudo', '-S', '-p', ''] if args.sudo_stdin else ['sudo', '-n']

    def ssh(command, privileged=False, data=None):
        remote = shlex.join(prefix + command) if privileged else command
        response = subprocess.run(['ssh', *OPTIONS, target, remote],
            input=(password + '\n') if privileged and password else data,
            capture_output=True, text=True, timeout=60)
        if response.returncode:
            raise RuntimeError('SSH check failed: ' + response.stderr[-1200:])
        return response.stdout

    def remote_script(script, payload):
        bootstrap = ('import io,sys; sys.stdin=io.StringIO(' + repr(json.dumps(payload))
                     + '); exec(' + repr(script) + ')\n')
        return json.loads(ssh("python3 -c 'import sys; exec(sys.stdin.readline())'", data=bootstrap))

    # Verify all deployed members of the frozen software manifest, before any RF.
    board_files = {destination(p): h for p, h in frozen['source_sha256'].items()
                   if p.startswith(('src/ps/', 'board/scripts/'))}
    verification = remote_script('''import hashlib,json,pathlib,sys
files=json.loads(sys.stdin.readline());root=pathlib.Path('/home/xilinx/sentinel')
for name,expected in files.items():
 if hashlib.sha256((root/name).read_bytes()).hexdigest()!=expected:raise RuntimeError('Frozen board input changed: '+name)
print(json.dumps({'verified_board_files':len(files)}))
''', board_files)
    record = {'started_at_pc': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
              'scope': 'Bounded paired-frame diagnosis, not an X1 acceptance/tuning round',
              'mode': args.mode, 'runner_sha256': sha(Path(__file__)),
              'frozen_software_manifest_sha256': sha(ROOT/'docs/x1_software_predeployment_r3.json'),
              **verification}
    if args.mode == 'deploy':
        previous = {}
        if args.replace_from_deployment:
            prior_path = args.replace_from_deployment.resolve()
            if sha(prior_path) != Path(str(prior_path)+'.sha256').read_text().split()[0]:
                raise RuntimeError('Previous deployment receipt hash mismatch')
            prior = json.loads(prior_path.read_text())
            if prior['status'] != 'PASS_DEPLOYMENT':
                raise RuntimeError('Previous deployment was not successful')
            previous = {item['local']: item['sha256'] for item in prior['files']}
            record['previous_deployment_sha256'] = sha(prior_path)
        stage = REMOTE + '/setup/' + tag
        ssh('mkdir ' + shlex.quote(stage))
        manifest = []
        for index, relative in enumerate(NEW_FILES):
            path = ROOT / relative
            staged = '%02d_%s' % (index, path.name)
            subprocess.run(['scp', *OPTIONS, str(path), target + ':' + stage + '/' + staged],
                           check=True, timeout=60)
            manifest.append({'local': relative, 'destination': destination(relative),
                             'staged': staged, 'sha256': sha(path),
                             'expected_previous_sha256': previous.get(relative)})
        script = '''import fcntl,hashlib,json,os,pathlib,sys
p=json.loads(sys.stdin.readline());root=pathlib.Path(p['root']);stage=pathlib.Path(p['stage'])
with open('/run/lock/zss_ad9361.lock','r') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 for item in p['files']:
  src=stage/item['staged'];dest=root/item['destination']
  if root not in dest.resolve().parents:raise RuntimeError('Destination outside board root')
  if hashlib.sha256(src.read_bytes()).hexdigest()!=item['sha256']:raise RuntimeError('Staged hash mismatch')
  compile(src.read_bytes(),str(src),'exec')
  if dest.exists():
   old=hashlib.sha256(dest.read_bytes()).hexdigest()
   if old!=item['sha256']:
    if old!=item.get('expected_previous_sha256'):raise RuntimeError('Different existing file: '+str(dest))
    backup=stage/('previous_'+old+'_'+dest.name)
    with backup.open('xb') as f:f.write(dest.read_bytes());f.flush();os.fsync(f.fileno())
    item['previous_sha256']=old
 for item in p['files']:
  src=stage/item['staged'];dest=root/item['destination']
  if not dest.exists() or hashlib.sha256(dest.read_bytes()).hexdigest()!=item['sha256']:
   temp=dest.with_name(dest.name+'.'+stage.name+'.tmp')
   with temp.open('xb') as f:f.write(src.read_bytes());f.flush();os.fsync(f.fileno())
   os.replace(str(temp),str(dest))
   fd=os.open(str(dest.parent),os.O_RDONLY|os.O_DIRECTORY)
   try:os.fsync(fd)
   finally:os.close(fd)
  if hashlib.sha256(dest.read_bytes()).hexdigest()!=item['sha256']:raise RuntimeError('Published hash mismatch')
print(json.dumps({'status':'PASS_DEPLOYMENT','files':p['files'],'hardware_accessed':False}))
'''
        record.update(remote_script(script, {'root': REMOTE, 'stage': stage, 'files': manifest}))
        write_evidence(output, record)
        print('PASS_DEPLOYMENT %s' % output.name, flush=True)
        return 0
    # Both new inputs must match their local source before starting a session.
    new_manifest = {destination(p): sha(ROOT / p) for p in NEW_FILES}
    remote_script('''import hashlib,json,pathlib,sys
for name,expected in json.loads(sys.stdin.readline()).items():
 if hashlib.sha256((pathlib.Path('/home/xilinx/sentinel')/name).read_bytes()).hexdigest()!=expected:raise RuntimeError('Diagnostic source mismatch')
print('{}')
''', new_manifest)
    record['diagnostic_sources_sha256'] = {p: sha(ROOT / p) for p in NEW_FILES}
    postflight = [PYTHON, '-I', REMOTE + '/scripts/x1_postflight.py']
    before = json.loads(ssh(postflight, privileged=True))
    if before['status'] != 'PASS':
        raise RuntimeError('Receiver must be stopped before diagnostic')
    record.update(preflight=before, boot_id_before=before['boot_id'],
                  user_confirmed_rx1a_tx_empty=args.confirm_rx1a_tx_empty)
    remote_output = REMOTE + '/measurements/' + tag + '.json'
    if ssh('test ! -e ' + remote_output + ' && test ! -e ' +
           remote_output[:-5] + '.npz && echo NEW_OUTPUT').strip() != 'NEW_OUTPUT':
        raise FileExistsError(remote_output)
    command = [PYTHON, '-I', REMOTE + '/scripts/run_x1_diagnostic.py',
               '--bit', REMOTE + '/overlay/sentinel_v1b/sentinel_v1b.bit',
               '--out', remote_output, '--source', args.mode, '--frames', str(args.frames)]
    record['command'] = command
    print('START %s frames=%d RF_TX=False' % (tag, args.frames), flush=True)
    with log.open('xb') as stream:
        process = subprocess.Popen(['ssh', *OPTIONS, target, shlex.join(prefix + command)],
            stdin=subprocess.PIPE, stdout=stream, stderr=subprocess.STDOUT)
        process.communicate((password + '\n').encode() if password else b'')
    record.update(ssh_exit_code=process.returncode,
                  ended_at_pc=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
                  log=log.relative_to(ROOT).as_posix(), log_sha256=sha(log))
    try:
        after = json.loads(ssh(postflight, privileged=True))
        record['postflight'] = after
        subprocess.run(['scp', *OPTIONS, target + ':' + remote_output, str(output)], check=True, timeout=60)
        data = json.loads(output.read_text())
        Path(str(output) + '.sha256').write_text(sha(output) + '  ' + output.name + '\n', encoding='ascii')
        record['result_sha256'] = sha(output)
        if data.get('raw_archive_sha256'):
            archive = output.with_suffix('.npz')
            subprocess.run(['scp', *OPTIONS, target + ':' + remote_output[:-5] + '.npz', str(archive)],
                           check=True, timeout=60)
            if sha(archive) != data['raw_archive_sha256']:
                raise RuntimeError('Raw power archive hash mismatch')
            record['archive_sha256'] = sha(archive)
            Path(str(archive) + '.sha256').write_text(sha(archive) + '  ' + archive.name + '\n', encoding='ascii')
        record['status'] = 'PASS_EXECUTION' if (process.returncode == 0 and data['status'] == 'completed'
            and data['boot_id'] == before['boot_id'] == after['boot_id'] and after['status'] == 'PASS'
            and record.get('archive_sha256') == data.get('raw_archive_sha256')) else 'FAIL_EXECUTION'
    except Exception as error:
        record.update(status='FAIL_POSTFLIGHT_OR_RETRIEVAL', error=str(error))
    password = None
    write_evidence(receipt, record)
    print(json.dumps(record, indent=2), flush=True)
    return 0 if record['status'] == 'PASS_EXECUTION' else 1


if __name__ == '__main__':
    raise SystemExit(main())
