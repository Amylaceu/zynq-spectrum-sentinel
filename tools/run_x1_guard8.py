"""Stage/run the single authorized guard=8 trial without changing frozen code.

Run deploy once, then capacity and station once each. Password is accepted only
on stdin. Each command/result/log has a new immutable tag and SHA256 receipt.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import shlex
import subprocess
import sys
from zoneinfo import ZoneInfo

from deploy_x1 import board_identity
from run_x1_board import ROOT, REMOTE, PYTHON, OPTIONS, sha, write_evidence

FILES = ('src/ps/sentinel/app/monitor_x1_guard8.py', 'board/scripts/run_x1_guard8.py')
FROZEN = ROOT/'docs/x1_software_predeployment_r3.json'


def verified(path):
    if sha(path) != Path(str(path)+'.sha256').read_text().split()[0]:
        raise ValueError('Evidence hash mismatch: '+str(path))
    return json.loads(path.read_text(encoding='utf-8-sig'))


def remote_name(relative):
    if relative.startswith('src/ps/'):
        return relative.removeprefix('src/')
    if relative.startswith('board/'):
        return relative.removeprefix('board/')
    raise ValueError('Not a deployable path')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('deploy', 'capacity', 'station'), required=True)
    parser.add_argument('--confirm-configuration-a', action='store_true', required=True)
    parser.add_argument('--sudo-stdin', action='store_true')
    args = parser.parse_args()
    tag = 'x1_guard8_'+args.mode
    receipt = ROOT/'board/measurements'/(tag+'_execution.json')
    output = ROOT/'board/measurements'/(tag+'.json')
    log = ROOT/'logs'/('X1_guard8_'+args.mode+'.log')
    if any(p.exists() or Path(str(p)+'.sha256').exists() for p in (receipt, output, log)):
        parser.error('One authorized trial only; preserve existing tag')
    frozen = verified(FROZEN)
    for name, digest in frozen['source_sha256'].items():
        if sha(ROOT/name) != digest:
            raise ValueError('Frozen source changed: '+name)
    simulation = verified(ROOT/'sim/results/x1_guard8_acceptance.json')
    if simulation['status'] != 'PASS':
        raise ValueError('Guard8 simulation must pass first')
    password = sys.stdin.readline().rstrip('\r\n') if args.sudo_stdin else None
    if args.sudo_stdin and not password:
        parser.error('Missing credential on stdin')
    target = board_identity()
    def ssh(command, privileged=False, payload=None, timeout=45):
        if privileged:
            prefix = ['sudo', '-S', '-p', ''] if args.sudo_stdin else ['sudo', '-n']
            command = shlex.join(prefix+command)
            payload = password+'\n' if password else None
        response = subprocess.run(['ssh', *OPTIONS, target, command], input=payload,
                                  capture_output=True, text=True, timeout=timeout)
        if response.returncode:
            raise RuntimeError('SSH failed: '+response.stderr[-1000:])
        return response.stdout
    boot = ssh('cat /proc/sys/kernel/random/boot_id').strip()
    before = json.loads(ssh([PYTHON, '-I', REMOTE+'/scripts/x1_postflight.py'], privileged=True))
    if before['status'] != 'PASS' or before['boot_id'] != boot:
        raise ValueError('Receiver must be stopped before this trial')
    frozen_remote = {remote_name(name): digest for name, digest in frozen['source_sha256'].items()
                     if name.startswith(('src/ps/', 'board/'))}
    audit_source = '''import hashlib,json,pathlib,sys
p=json.load(sys.stdin);root=pathlib.Path(p['root'])
for name,digest in p['files'].items():
 if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Frozen board source differs: '+name)
print('FROZEN_BOARD_PASS')
'''
    ssh(shlex.join(['python3', '-c', audit_source]), payload=json.dumps(dict(root=REMOTE, files=frozen_remote)))
    sources = {name: sha(ROOT/name) for name in (*FILES, 'tools/run_x1_guard8.py')}
    record = dict(started_at_pc=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
                  user_authorized_one_additional_trial=True, configuration_a_confirmed=True,
                  antenna='New same-band antenna; RX1A connected, TX empty', preflight=before,
                  boot_id_before=boot, source_sha256=sources,
                  frozen_manifest_sha256=sha(FROZEN), frozen_board_sources_checked=len(frozen_remote),
                  simulation_sha256=sha(ROOT/'sim/results/x1_guard8_acceptance.json'))
    if args.mode == 'deploy':
        stage = REMOTE+'/setup/x1_guard8'
        ssh('mkdir '+stage)
        entries = []
        for name in FILES:
            path = ROOT/name
            subprocess.run(['scp', *OPTIONS, str(path), target+':'+stage+'/'+path.name], check=True, timeout=40)
            entries.append(dict(staged=path.name, destination=remote_name(name), sha256=sha(path)))
        installer = '''import fcntl,hashlib,json,os,pathlib,sys
p=json.load(sys.stdin);root=pathlib.Path(p['root']);stage=pathlib.Path(p['stage'])
with open('/run/lock/zss_ad9361.lock','r') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 for item in p['files']:
  src=stage/item['staged'];dst=root/item['destination']
  if dst.exists() or root not in dst.resolve().parents:raise RuntimeError('Refuse overwrite/invalid path')
  if hashlib.sha256(src.read_bytes()).hexdigest()!=item['sha256']:raise RuntimeError('Staged hash mismatch')
  compile(src.read_bytes(),str(src),'exec')
 for item in p['files']:
  dst=root/item['destination']
  with dst.open('xb') as out:
   out.write((stage/item['staged']).read_bytes());out.flush();os.fsync(out.fileno())
  if hashlib.sha256(dst.read_bytes()).hexdigest()!=item['sha256']:raise RuntimeError('Published hash mismatch')
 print(json.dumps({'status':'PASS','files':p['files'],'hardware_accessed':False}))
'''
        deployment = json.loads(ssh(shlex.join(['python3', '-c', installer]), payload=json.dumps(
            dict(root=REMOTE, stage=stage, files=entries))))
        record.update(status='PASS_DEPLOYMENT', deployment=deployment)
        write_evidence(receipt, record)
        print(json.dumps(record, indent=2))
        return 0
    deployment = verified(ROOT/'board/measurements/x1_guard8_deploy_execution.json')
    if deployment['status'] != 'PASS_DEPLOYMENT' or deployment['source_sha256'] != sources:
        raise ValueError('Deployment source association mismatch')
    for name in FILES:
        if ssh('sha256sum '+REMOTE+'/'+remote_name(name)).split()[0] != sources[name]:
            raise ValueError('Board trial source changed')
    remote_output = REMOTE+'/measurements/'+tag+'.json'
    if ssh('test ! -e '+remote_output+' && echo NEW_OUTPUT').strip() != 'NEW_OUTPUT':
        raise FileExistsError(remote_output)
    command = [PYTHON, '-I', REMOTE+'/scripts/run_x1_guard8.py', '--bit',
               REMOTE+'/overlay/sentinel_v1b/sentinel_v1b.bit', '--out', remote_output,
               '--lo', str(98000000 if args.mode == 'capacity' else 96400000)]
    sudo = ['sudo', '-S', '-p', ''] if args.sudo_stdin else ['sudo', '-n']
    record['command'] = command
    print('START '+tag+' 120s RX only', flush=True)
    with log.open('xb') as stream:
        process = subprocess.Popen(['ssh', *OPTIONS, target, shlex.join(sudo+command)],
                                   stdin=subprocess.PIPE, stdout=stream, stderr=subprocess.STDOUT)
        process.communicate((password+'\n').encode() if password else b'')
    record.update(ssh_exit_code=process.returncode, log=log.relative_to(ROOT).as_posix(),
                  log_sha256=sha(log), ended_at_pc=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat())
    try:
        after = json.loads(ssh([PYTHON, '-I', REMOTE+'/scripts/x1_postflight.py'], privileged=True))
        record['postflight'] = after
        subprocess.run(['scp', *OPTIONS, target+':'+remote_output, str(output)], check=True, timeout=40)
        Path(str(output)+'.sha256').write_text(sha(output)+'  '+output.name+'\n', encoding='ascii')
        data = json.loads(output.read_text())
        record.update(result_sha256=sha(output), result_status=data['status'])
        passed = (process.returncode == 0 and data['status'] == 'completed'
                  and data['boot_id'] == boot and after['boot_id'] == boot and after['status'] == 'PASS')
        record['status'] = 'PASS_EXECUTION' if passed else 'FAIL_EXECUTION'
    except Exception as error:
        record.update(status='FAIL_POSTFLIGHT_OR_RETRIEVAL', error=str(error))
    password = None
    write_evidence(receipt, record)
    print(json.dumps(record, indent=2), flush=True)
    return 0 if record['status'] == 'PASS_EXECUTION' else 1


if __name__ == '__main__':
    raise SystemExit(main())
