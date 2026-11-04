"""Deploy a finite RX-only interface regression; no reload or TX operation."""
import argparse
import ast
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile

from run_x5_board import payload_files, INSTALL, LIB_SHA
from x2_transport import ROOT, REMOTE, PYTHON, OPTIONS, Transport, sha, verified, write_evidence
from x5_transfer import retrieve_files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--preflight-bit', required=True)
    parser.add_argument('--confirm-configuration-a', action='store_true', required=True)
    parser.add_argument('--sudo-stdin', action='store_true')
    args = parser.parse_args()
    password = sys.stdin.readline().rstrip('\r\n') if args.sudo_stdin else None
    if args.sudo_stdin and not password:
        parser.error('Missing credential')
    tag = 'y3_v2_rx_interface_r%d' % args.attempt
    out = ROOT/'board/measurements'/tag
    execution = out.with_name(tag+'_execution.json')
    log = ROOT/'logs'/(tag+'.log')
    archive = ROOT/'build'/(tag+'_runtime.tar.gz')
    if any(p.exists() for p in (out, execution, log, archive)):
        raise FileExistsError('Preserve prior attempt')
    files = payload_files('sentinel_v2_100m')
    script = ROOT/'board/scripts/check_v2_rx_interface.py'
    ast.parse(script.read_text(), feature_version=(3, 8))
    files['scripts/check_v2_rx_interface.py'] = script
    manifest = {name: sha(path) for name, path in files.items()}
    with tarfile.open(archive, 'x:gz') as package:
        for name, path in files.items():
            package.add(path, arcname=name, recursive=False)
    stage = REMOTE+'/setup/'+tag+'_runtime'
    transport = Transport(password)
    transport.ssh(['test', '!', '-e', stage])
    transport.ssh(['test', '!', '-e', stage+'.tar.gz'])
    transport.copy(archive, transport.target+':'+stage+'.tar.gz')
    transport.ssh([PYTHON, '-I', '-c', INSTALL], payload=json.dumps(dict(
        root=stage, archive=stage+'.tar.gz', archive_sha256=sha(archive), files=manifest)))
    def stopped():
        return json.loads(transport.ssh([PYTHON, '-I', stage+'/scripts/y3_postflight.py',
                          '--bit', args.preflight_bit], privileged=True))
    preflight = stopped()
    if preflight['status'] != 'PASS':
        raise ValueError('Hardware not idle')
    library = REMOTE+'/ps/libad9361_pynq/libad9361_pynq.so'
    if transport.ssh(['sha256sum', library]).split()[0] != LIB_SHA:
        raise ValueError('Library differs from baseline')
    command = ['timeout', '--signal=TERM', '--kill-after=10s', '35s', PYTHON, '-I',
        stage+'/scripts/check_v2_rx_interface.py', '--bit', args.preflight_bit,
        '--library', library, '--out', stage+'/measurements/result.json']
    record = dict(status='STARTED', preflight=preflight, command=command,
                  deployment_sha256=manifest, archive_sha256=sha(archive),
                  runner_sha256=sha(Path(__file__)), TX_requested=False)
    write_evidence(out.with_name(tag+'_start.json'), record)
    try:
        with log.open('xb') as stream:
            process = subprocess.run(['ssh', *OPTIONS, transport.target,
                shlex.join(transport.privileged(command))],
                input=(password+'\n').encode() if password else b'',
                stdout=stream, stderr=subprocess.STDOUT, timeout=65)
        record['ssh_exit_code'] = process.returncode
        record['postflight'] = stopped()
        out.mkdir()
        retrieve_files(transport.target, stage+'/measurements',
                       ['result.json', 'result.json.sha256'], out, OPTIONS)
        result = verified(out/'result.json')
        if not (process.returncode == 0 and result['status'] == 'PASS'
                and record['postflight']['status'] == 'PASS'
                and result['boot_id'] == preflight['boot_id'] == record['postflight']['boot_id']):
            raise RuntimeError('RX execution/cleanup failed')
        record.update(status='PASS', result_sha256=sha(out/'result.json'))
    except Exception as error:
        record.update(status='FAIL', error=repr(error))
    finally:
        record['log_sha256'] = sha(log) if log.exists() else None
        write_evidence(execution, record)
    print(json.dumps(dict(status=record['status'], execution=str(execution))))
    if record['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
