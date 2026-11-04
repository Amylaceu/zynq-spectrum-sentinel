"""Deploy X5/v2 into a new isolated root and run one bounded receive-only trial.

Requires audited v1d or v2, explicit configuration-A authorization and immutable
local build evidence. Optional sudo password is read only from stdin, never saved.
No existing board source, bitstream or shared library is overwritten.
"""
import argparse
import ast
from datetime import datetime, timezone
import json
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import sys
import tarfile

import numpy as np

from freeze_x5_build import verify
from x5_runtime_patch import check_runtime_patch
from x2_transport import ROOT, REMOTE, PYTHON, OPTIONS, Transport, sha, verified, write_evidence
from x5_transfer import retrieve_files

LIB_SHA = 'b329018314e6ecc9c0b11440b0d5449d9670fda7b5d37deabdc55c4731616e83'
MODEL_SHA = '5e752f90523ea92d95bbd0ac3fe40ff70c12d9f0023373c36c22acd495508935'


def verify_captures(directory, result):
    """Independently decode saved SCAP words rather than trusting execution exit."""
    checks = []
    for record in result['records']:
        name = record['capture_filename']
        if PurePosixPath(name).name != name or not name.endswith('.npz'):
            raise ValueError('Unsafe capture filename')
        path = directory/name
        digest = sha(path)
        if digest != record['capture_sha256'] or digest != Path(str(path)+'.sha256').read_text().split()[0]:
            raise ValueError('Capture digest mismatch')
        with np.load(path, allow_pickle=False) as data:
            words = data['words']
            if words.dtype != np.dtype('uint32') or words.shape != (4104,):
                raise ValueError('SCAP length/type mismatch')
            expected = (0x53434150, record['channel'], record['fcw'], 1, 4096, 0)
            if tuple(int(words[i]) for i in (0, 3, 4, 5, 6, 7)) != expected:
                raise ValueError('SCAP header mismatch')
            timestamp = int(words[1]) | int(words[2]) << 32
            if timestamp != record['pl_timestamp_cycles'] or timestamp != int(data['timestamp_cycles']):
                raise ValueError('SCAP timestamp mismatch')
            i = (words[8:] & 65535).astype(np.uint16).view(np.int16).astype(np.float32)
            q = (words[8:] >> 16).astype(np.uint16).view(np.int16).astype(np.float32)
            if int(data['fs_hz']) != 480000 or not np.array_equal(data['iq'], (i+1j*q)/32768):
                raise ValueError('SCAP IQ/sample rate mismatch')
            checks.append(dict(filename=name, sha256=digest, words=4104, samples=4096,
                               timestamp_cycles=timestamp))
    return checks


def payload_files(image='sentinel_v1d'):
    if image not in ('sentinel_v1d', 'sentinel_v2_100m'):
        raise ValueError('Unsupported X5 monitor image')
    files = {}
    for path in sorted((ROOT/'src/ps/sentinel').rglob('*.py')):
        ast.parse(path.read_text(encoding='utf-8'), feature_version=(3, 8))
        files[path.relative_to(ROOT/'src').as_posix()] = path
    for name in ('run_x5_monitor.py', 'x5_postflight.py', 'y3_postflight.py'):
        path = ROOT/'board/scripts'/name
        ast.parse(path.read_text(), feature_version=(3, 8))
        files['scripts/'+name] = path
    model = ROOT/'src/ps/models/weights/amc_v2/round_3/model.npz'
    if sha(model) != MODEL_SHA:
        raise ValueError('Model differs from frozen candidate')
    files['ps/models/weights/amc_v2/round_3/model.npz'] = model
    bundle = ROOT/'board/overlay'/image
    acceptance = verified(bundle/'acceptance.json')
    if acceptance['status'] != 'PASS' or acceptance['image'] != image:
        raise ValueError('Require full implementation acceptance')
    if image == 'sentinel_v2_100m':
        sys.path.insert(0, str(ROOT/'src/ps'))
        from sentinel.v_y3 import checked_y3_bundle
        from run_y3_board import verify_v2_inputs
        checked_y3_bundle(bundle/(image+'.bit'), image=image)
        verify_v2_inputs(acceptance)
    for suffix in ('.bit', '.hwh', '.xsa'):
        path = bundle/(image+suffix)
        if sha(path) != acceptance['artifacts_sha256'][path.name]:
            raise ValueError('Implementation artifact changed')
        files['overlay/'+image+'/'+path.name] = path
    for name in ('acceptance.json', 'acceptance.json.sha256', 'sha256.txt'):
        files['overlay/'+image+'/'+name] = bundle/name
    if acceptance.get('deployment_policy') == 'development_nonnegative_v1':
        for name in ('development_review.json', 'development_review.json.sha256'):
            files['overlay/'+image+'/'+name] = bundle/name
    return files


INSTALL = '''import fcntl,hashlib,json,os,pathlib,sys,tarfile
p=json.load(sys.stdin);root=pathlib.Path(p['root']);archive=pathlib.Path(p['archive'])
if hashlib.sha256(archive.read_bytes()).hexdigest()!=p['archive_sha256']:raise ValueError('Archive digest')
with open('/run/lock/zss_ad9361.lock','r') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 root.mkdir(exist_ok=False)
 with tarfile.open(str(archive)) as tar:
  entries=tar.getmembers()
  if sorted(m.name for m in entries)!=sorted(p['files']):raise ValueError('Unexpected tar members')
  for member in entries:
   relative=pathlib.PurePosixPath(member.name)
   if not member.isfile() or relative.is_absolute() or '..' in relative.parts:raise ValueError('Unsafe member')
   destination=root/member.name;destination.parent.mkdir(parents=True,exist_ok=True)
   data=tar.extractfile(member).read()
   if hashlib.sha256(data).hexdigest()!=p['files'][member.name]:raise ValueError('Payload digest')
   if destination.suffix=='.py':compile(data,str(destination),'exec')
   with destination.open('xb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
   os.utime(str(destination),(member.mtime,member.mtime))
 (root/'measurements').mkdir()
 fd=os.open(str(root),os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
print('X5_ISOLATED_DEPLOYMENT_PASS')
'''

CHECK = '''import hashlib,json,pathlib,sys
p=json.load(sys.stdin);root=pathlib.Path(p['root'])
for name,digest in p['files'].items():
 if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise ValueError('Board file differs: '+name)
sys.path.insert(0,str(root/'ps'))
import sentinel.app.monitor_x5,numpy,PIL
for name,module in list(sys.modules.items()):
 if name=='sentinel' or name.startswith('sentinel.'):
  filename=getattr(module,'__file__',None)
  if filename is None:continue
  path=pathlib.Path(filename);relative=path.relative_to(root).as_posix()
  if relative not in p['files']:raise ValueError('Unstaged import '+relative)
print(json.dumps(dict(python=sys.version,numpy=numpy.__version__,status='PASS')))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--image', choices=('sentinel_v1d', 'sentinel_v2_100m'),
                        default='sentinel_v1d')
    parser.add_argument('--implementation-attempt', type=int, choices=(1, 2, 3), default=1)
    parser.add_argument('--runtime-manifest', type=Path,
                        help='PS-only patch bound to the original hardware acceptance')
    parser.add_argument('--confirm-configuration-a', action='store_true', required=True)
    parser.add_argument('--sudo-stdin', action='store_true')
    parser.add_argument('--lo', type=int, choices=(98000000, 96400000), default=98000000)
    parser.add_argument('--seconds', type=int, choices=(30, 120, 300), default=120)
    parser.add_argument('--listen', type=float, help='Optional FM station Hz on v2')
    parser.add_argument('--volume', type=float, default=-21)
    parser.add_argument('--preflight-bit', default=REMOTE+'/overlay/sentinel_v1b/sentinel_v1b.bit')
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT/'src/ps'))
    from sentinel.listen_y3 import validate_listen, evaluate_listening
    try:
        validate_listen(args.image, args.listen, args.lo, args.volume)
    except ValueError as error:
        parser.error(str(error))
    password = sys.stdin.readline().rstrip('\r\n') if args.sudo_stdin else None
    if args.sudo_stdin and not password:
        parser.error('Missing sudo credential')
    if args.image == 'sentinel_v1d':
        if args.runtime_manifest:
            check_runtime_patch(args.runtime_manifest, args.implementation_attempt)
        else:
            prebuild_path, _ = verify(args.implementation_attempt)
            accepted = verified(ROOT/'board/overlay/sentinel_v1d/acceptance.json')
            if accepted['prebuild_manifest_sha256'] != sha(prebuild_path):
                raise ValueError('Implementation label does not match hardware acceptance')
    elif args.runtime_manifest:
        parser.error('The v1d PS-only runtime manifest cannot authorize v2')
    tag = ('x5_' if args.image == 'sentinel_v1d' else 'v2_x5_') + (
        '%s_r%d' % ('formal' if args.lo == 98000000 else 'station', args.attempt))
    if args.listen is not None:
        tag = 'y3_v2_integrated_%ds_r%d' % (args.seconds, args.attempt)
    output = ROOT/'board/measurements'/tag
    receipt = output.with_name(tag+'_execution.json')
    log = ROOT/'logs'/(tag.replace('x5_', 'X5_')+'.log')
    if output.exists() or receipt.exists() or log.exists():
        raise FileExistsError('Preserve previous trial')
    files = payload_files(args.image)
    manifest = {name: sha(path) for name, path in files.items()}
    stage = REMOTE+'/setup/'+tag+'_runtime'
    archive = ROOT/'build'/(tag+'_runtime.tar.gz')
    if archive.exists():
        raise FileExistsError(archive)
    with tarfile.open(archive, 'x:gz') as tar:
        for name, path in files.items():
            tar.add(path, arcname=name, recursive=False)
    transport = Transport(password)
    remote_archive = stage+'.tar.gz'
    transport.ssh(['test', '!', '-e', remote_archive])
    transport.ssh(['test', '!', '-e', stage])
    transport.copy(archive, transport.target+':'+remote_archive)
    transport.ssh([PYTHON, '-I', '-c', INSTALL], payload=json.dumps(dict(
        root=stage, archive=remote_archive, archive_sha256=sha(archive), files=manifest)))
    dependencies = json.loads(transport.ssh([PYTHON, '-I', '-c', CHECK],
        payload=json.dumps(dict(root=stage, files=manifest))))
    def stopped(bit):
        script = 'x5_postflight.py' if args.image == 'sentinel_v1d' else 'y3_postflight.py'
        return json.loads(transport.ssh([PYTHON, '-I', stage+'/scripts/'+script,
                                       '--bit', bit], privileged=True))
    preflight = stopped(args.preflight_bit)
    if preflight['status'] != 'PASS':
        raise ValueError('Require stopped preflight')
    library = REMOTE+'/ps/libad9361_pynq/libad9361_pynq.so'
    library_before = transport.ssh(['sha256sum', library]).split()[0]
    if library_before != LIB_SHA:
        raise ValueError('RF library differs from audited baseline')
    bit = stage+'/overlay/'+args.image+'/'+args.image+'.bit'
    remote_output = stage+'/measurements/'+tag
    command = [PYTHON, '-I', stage+'/scripts/run_x5_monitor.py', '--bit', bit,
               '--image', args.image,
               '--model', stage+'/ps/models/weights/amc_v2/round_3/model.npz',
               '--out', remote_output, '--lo', str(args.lo), '--seconds', str(args.seconds)]
    if args.lo == 96400000:
        command += ['--fm-truth-hz', '95800000']
    if args.listen is not None:
        command += ['--listen', str(args.listen), '--volume', str(args.volume)]
    record = dict(status='STARTED', started_at_pc=datetime.now(timezone.utc).isoformat(),
                  image=args.image,
                  listen_station_hz=args.listen, analog_volume_db=args.volume,
                  hardware_implementation_attempt=args.implementation_attempt,
                  runtime_manifest_sha256=sha(args.runtime_manifest) if args.runtime_manifest else None,
                  scope='Execution and raw packet integrity only; separate acceptance evaluates targets',
                  configuration_a_confirmed=True, RF_TX_requested=False, remote_root=stage,
                  deployment_sha256=manifest, archive_sha256=sha(archive), dependencies=dependencies,
                  preflight=preflight, library_sha256_before=library_before,
                  host_runner_sha256=sha(Path(__file__)), command=command)
    # Retain the deployment/command before hardware access, even if SSH fails.
    write_evidence(output.with_name(tag+'_start.json'), record)
    print('X5_RECEIVE_START '+tag, flush=True)
    try:
        with log.open('xb') as stream:
            process = subprocess.run(['ssh', *OPTIONS, transport.target,
                shlex.join(transport.privileged(command))],
                input=(password+'\n').encode() if password else b'',
                stdout=stream, stderr=subprocess.STDOUT, timeout=args.seconds+120)
        record['ssh_exit_code'] = process.returncode
    except Exception as error:
        record.update(ssh_exit_code=None, execution_error=str(error))
    finally:
        record['log_sha256'] = sha(log) if log.exists() else None
        # Never retry a failed DMA in the same loaded image.
        try:
            record['postflight'] = stopped(bit)
        except Exception as error:
            record['postflight_error'] = str(error)
        try:
            transport.copy(transport.target+':'+remote_output+'/result.json',
                           str(output.with_name(tag+'_result_probe.json')))
            # Retrieval is bounded to the files explicitly named in result.json.
            result = json.loads(output.with_name(tag+'_result_probe.json').read_text())
            output.mkdir(exist_ok=False)
            names = ['result.json', 'result.json.sha256']
            for item in result['records']:
                name = item['capture_filename']
                if PurePosixPath(name).name != name or not name.endswith('.npz'):
                    raise ValueError('Unsafe remote capture name')
                names += [name, name+'.sha256']
            # Batches avoid per-file handshakes and Windows command-line overflow.
            retrieve_files(transport.target, remote_output, names, output, OPTIONS)
            result = verified(output/'result.json')
            record['capture_checks'] = verify_captures(output, result)
            record['result_sha256'] = sha(output/'result.json')
            record['library_sha256_after'] = transport.ssh(['sha256sum', library]).split()[0]
            transport.ssh([PYTHON, '-I', '-c', CHECK], payload=json.dumps(dict(root=stage, files=manifest)))
            post = record.get('postflight', {})
            passed = (record['ssh_exit_code'] == 0 and result['status'] == 'completed'
                      and post.get('status') == 'PASS' and post['boot_id'] == preflight['boot_id']
                      and result['boot_id'] == preflight['boot_id']
                      and record['library_sha256_after'] == library_before)
            if args.listen is not None:
                record['audio_checks'] = evaluate_listening(result, args.seconds)
                record['human_listening'] = 'PENDING'
                passed = passed and all(record['audio_checks'].values())
            record['status'] = 'PASS_EXECUTION' if passed else 'FAIL_EXECUTION'
        except Exception as error:
            record.update(status='FAIL_RETRIEVAL_OR_POSTFLIGHT', retrieval_error=str(error))
        record['ended_at_pc'] = datetime.now(timezone.utc).isoformat()
        write_evidence(receipt, record)
    print(json.dumps(record, indent=2), flush=True)
    return 0 if record['status'] == 'PASS_EXECUTION' else 1


if __name__ == '__main__':
    raise SystemExit(main())
