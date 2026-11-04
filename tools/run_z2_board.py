"""Deploy audited Z2 to an isolated root; run a bounded configuration-A UI check.

Preserves prior v1d station results and models. No transmit operation, firmware
rebuild, overwrite of existing deployment, or automatic acceptance of visuals.
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

from freeze_z2_build import verify
from run_x5_board import CHECK, INSTALL, LIB_SHA, MODEL_SHA, verify_captures
from x2_transport import ROOT, REMOTE, PYTHON, OPTIONS, Transport, sha, verified, write_evidence
from x5_transfer import retrieve_files


def payload_files(implementation_attempt):
    prebuild, _ = verify(implementation_attempt)
    bundle = ROOT/'board/overlay/sentinel_z2'
    accepted = verified(bundle/'acceptance.json')
    if (accepted.get('status') != 'PASS' or accepted.get('image') != 'sentinel_z2'
            or accepted['prebuild_manifest_sha256'] != sha(prebuild)):
        raise ValueError('Require audited Z2 and its unchanged frozen build inputs')
    files = {}
    for path in sorted((ROOT/'src/ps/sentinel').rglob('*.py')):
        ast.parse(path.read_text(encoding='utf-8'), feature_version=(3, 8))
        files[path.relative_to(ROOT/'src').as_posix()] = path
    for name in ('run_z2_monitor.py', 'z2_postflight.py'):
        path = ROOT/'board/scripts'/name
        ast.parse(path.read_text(), feature_version=(3, 8))
        files['scripts/'+name] = path
    model = ROOT/'src/ps/models/weights/amc_v2/round_3/model.npz'
    if sha(model) != MODEL_SHA:
        raise ValueError('Experimental model changed')
    files['ps/models/weights/amc_v2/round_3/model.npz'] = model
    for suffix in ('bit', 'hwh', 'xsa'):
        path = bundle/('sentinel_z2.'+suffix)
        if sha(path) != accepted['artifacts_sha256'].get(path.name):
            raise ValueError('Accepted artifact changed: '+path.name)
        files['overlay/sentinel_z2/'+path.name] = path
    for name in ('acceptance.json', 'acceptance.json.sha256', 'sha256.txt'):
        files['overlay/sentinel_z2/'+name] = bundle/name
    return files, sha(prebuild), sha(bundle/'acceptance.json')


def checked_capture_names(result):
    names = ['result.json', 'result.json.sha256']
    for item in result['records']:
        name = item['capture_filename']
        if (PurePosixPath(name).name != name or '/' in name or '\\' in name
                or not name.endswith('.npz')):
            raise ValueError('Unsafe remote capture filename')
        names.extend((name, name+'.sha256'))
    if len(names) != len(set(names)):
        raise ValueError('Duplicate capture filename')
    return names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--implementation-attempt', type=int, choices=(1, 2, 3), default=1)
    parser.add_argument('--confirm-configuration-a', action='store_true', required=True)
    parser.add_argument('--sudo-stdin', action='store_true')
    parser.add_argument('--seconds', type=int, choices=(120, 600), default=600)
    parser.add_argument('--preflight-bit',
                        help='Exact already-loaded, accepted v1d or Z2 bit path')
    args = parser.parse_args()
    password = sys.stdin.readline().rstrip('\r\n') if args.sudo_stdin else None
    if args.sudo_stdin and not password:
        parser.error('Missing sudo credential')
    if args.preflight_bit:
        prior_bit = args.preflight_bit
    else:
        prior = verified(ROOT/'board/measurements/x5_station_r3_execution.json')
        if prior['status'] != 'PASS_EXECUTION':
            raise ValueError('Missing accepted prior execution')
        prior_bit = prior['remote_root']+'/overlay/sentinel_v1d/sentinel_v1d.bit'
    tag = 'z2_ui_r%d' % args.attempt
    output = ROOT/'board/measurements'/tag
    start = output.with_name(tag+'_start.json')
    receipt = output.with_name(tag+'_execution.json')
    log = ROOT/'logs'/('Y2_'+tag+'.log')
    archive = ROOT/'build'/(tag+'_runtime.tar.gz')
    if any(path.exists() for path in (output, start, receipt, log, archive)):
        raise FileExistsError('Preserve prior Z2 deployment and evidence')
    files, pre_sha, accepted_sha = payload_files(args.implementation_attempt)
    manifest = {name: sha(path) for name, path in files.items()}
    stage = REMOTE+'/setup/'+tag+'_runtime'
    with tarfile.open(archive, 'x:gz') as tar:
        for name, path in files.items():
            tar.add(path, arcname=name, recursive=False)
    transport = Transport(password)
    remote_archive = stage+'.tar.gz'
    transport.ssh(['test', '!', '-e', stage])
    transport.ssh(['test', '!', '-e', remote_archive])
    transport.copy(archive, transport.target+':'+remote_archive)
    transport.ssh([PYTHON, '-I', '-c', INSTALL], payload=json.dumps(dict(
        root=stage, archive=remote_archive, archive_sha256=sha(archive), files=manifest)))
    check = CHECK.replace('sentinel.app.monitor_x5', 'sentinel.app.monitor_z2')
    dependencies = json.loads(transport.ssh([PYTHON, '-I', '-c', check],
        payload=json.dumps(dict(root=stage, files=manifest))))

    def stopped(bit):
        return json.loads(transport.ssh([PYTHON, '-I', stage+'/scripts/z2_postflight.py',
                                        '--bit', bit], privileged=True))

    preflight = stopped(prior_bit)
    if preflight['status'] != 'PASS':
        raise ValueError('Require stopped, accepted prior image')
    library = REMOTE+'/ps/libad9361_pynq/libad9361_pynq.so'
    if transport.ssh(['sha256sum', library]).split()[0] != LIB_SHA:
        raise ValueError('RF library differs from baseline')
    bit = stage+'/overlay/sentinel_z2/sentinel_z2.bit'
    remote_output = stage+'/measurements/'+tag
    command = [PYTHON, '-I', stage+'/scripts/run_z2_monitor.py', '--bit', bit,
               '--model', stage+'/ps/models/weights/amc_v2/round_3/model.npz',
               '--out', remote_output, '--lo', '96400000', '--seconds', str(args.seconds),
               '--fm-truth-hz', '95800000']
    record = dict(status='STARTED', started_at_pc=datetime.now(timezone.utc).isoformat(),
                  scope='Z2 UI integration only; prior Y2 FAIL preserved; no retuning or training',
                  configuration='A', RF_TX_requested=False, human_visual='PENDING',
                  hardware_implementation_attempt=args.implementation_attempt,
                  prebuild_sha256=pre_sha, acceptance_sha256=accepted_sha,
                  deployment_sha256=manifest, archive_sha256=sha(archive),
                  remote_root=stage, dependencies=dependencies, preflight=preflight,
                  runner_sha256=sha(Path(__file__)), command=command)
    write_evidence(start, record)
    print('Z2_RECEIVE_START '+tag, flush=True)
    try:
        with log.open('xb') as stream:
            process = subprocess.run(['ssh', *OPTIONS, transport.target,
                shlex.join(transport.privileged(command))],
                input=(password+'\n').encode() if password else b'',
                stdout=stream, stderr=subprocess.STDOUT, timeout=args.seconds+120)
        record['ssh_exit_code'] = process.returncode
    except Exception as error:
        record['execution_error'] = str(error)
    finally:
        record['status'] = 'FAIL_EXECUTION'
        try:
            record['postflight'] = stopped(bit)
            output.mkdir(exist_ok=False)
            retrieve_files(transport.target, remote_output,
                           ['result.json', 'result.json.sha256'], output, OPTIONS)
            result = verified(output/'result.json')
            names = checked_capture_names(result)[2:]
            if names:
                retrieve_files(transport.target, remote_output, names, output, OPTIONS)
            record['capture_checks'] = verify_captures(output, result)
            record['result_sha256'] = sha(output/'result.json')
            record['library_sha256_after'] = transport.ssh(['sha256sum', library]).split()[0]
            transport.ssh([PYTHON, '-I', '-c', check],
                          payload=json.dumps(dict(root=stage, files=manifest)))
            post = record['postflight']
            if (record.get('ssh_exit_code') == 0 and result['status'] == 'completed'
                    and post['status'] == 'PASS' and post['boot_id'] == preflight['boot_id']
                    and result['boot_id'] == preflight['boot_id']
                    and record['library_sha256_after'] == LIB_SHA):
                record['status'] = 'PASS_EXECUTION_AWAITING_HUMAN'
        except Exception as error:
            record['retrieval_or_postflight_error'] = str(error)
        record['ended_at_pc'] = datetime.now(timezone.utc).isoformat()
        record['log_sha256'] = sha(log) if log.exists() else None
        write_evidence(receipt, record)
        print('Z2_RECEIVE_ENDED '+record['status'], flush=True)
    if record['status'] != 'PASS_EXECUTION_AWAITING_HUMAN':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
