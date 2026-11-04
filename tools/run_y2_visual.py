"""One bounded human visual check using the EXACT prior measured deployment.

No tuning, training, new firmware or new quantitative acceptance attempt.
The earlier FAIL statistics are immutable. Only configuration A is supported.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import sys

from run_x5_board import CHECK, LIB_SHA, verify_captures
from x2_transport import ROOT, REMOTE, PYTHON, OPTIONS, Transport, sha, verified, write_evidence
from x5_transfer import retrieve_files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sudo-stdin', action='store_true')
    parser.add_argument('--confirm-configuration-a', action='store_true', required=True)
    args = parser.parse_args()
    password = sys.stdin.readline().rstrip('\r\n') if args.sudo_stdin else None
    if args.sudo_stdin and not password:
        parser.error('Missing sudo credential')
    transport = Transport(password)
    receipt_path = ROOT/'board/measurements/x5_station_r3_execution.json'
    receipt = verified(receipt_path)
    if receipt['status'] != 'PASS_EXECUTION':
        raise ValueError('Require the original successful execution receipt')
    stage = receipt['remote_root']
    if stage != REMOTE+'/setup/x5_station_r3_runtime':
        raise ValueError('Unexpected original deployment')
    output = ROOT/'board/measurements/y2_visual_1'
    start_path = output.with_name(output.name+'_start.json')
    final_path = output.with_name(output.name+'_execution.json')
    log = ROOT/'logs/Y2_visual_1.log'
    if any(path.exists() for path in (output, start_path, final_path, log)):
        raise FileExistsError('Preserve previous human visual check')
    dependencies = transport.ssh([PYTHON, '-I', '-c', CHECK], payload=json.dumps(dict(
        root=stage, files=receipt['deployment_sha256'])))
    bit = stage+'/overlay/sentinel_v1d/sentinel_v1d.bit'
    postflight_command = [PYTHON, '-I', stage+'/scripts/x5_postflight.py', '--bit', bit]
    preflight = json.loads(transport.ssh(postflight_command, privileged=True))
    if preflight['status'] != 'PASS':
        raise ValueError('Require stopped and matched prior image')
    library = REMOTE+'/ps/libad9361_pynq/libad9361_pynq.so'
    if transport.ssh(['sha256sum', library]).split()[0] != LIB_SHA:
        raise ValueError('RF library differs from measured deployment')
    remote_output = stage+'/measurements/y2_visual_1'
    transport.ssh(['test', '!', '-e', remote_output])
    command = [PYTHON, '-I', stage+'/scripts/run_x5_monitor.py', '--bit', bit,
               '--model', stage+'/ps/models/weights/amc_v2/round_3/model.npz',
               '--out', remote_output, '--lo', '96400000', '--seconds', '600',
               '--fm-truth-hz', '95800000']
    record = dict(schema='y2-visual-execution-v1', status='STARTED',
                  recorded_at_pc=datetime.now(timezone.utc).isoformat(),
                  scope='Human visual check only; does not replace previous failed quantitative trial',
                  source_receipt_sha256=sha(receipt_path), runner_sha256=sha(Path(__file__)),
                  configuration='A', RF_TX_requested=False, human_visual='PENDING',
                  remote_root=stage, command=command, preflight=preflight,
                  dependencies=dependencies.strip())
    write_evidence(start_path, record)
    print('Y2_VISUAL_STARTED 600s exact station_r3 deployment', flush=True)
    try:
        with log.open('xb') as stream:
            proc = subprocess.run(['ssh', *OPTIONS, transport.target,
                                   shlex.join(transport.privileged(command))],
                                  input=(password+'\n').encode() if password else b'',
                                  stdout=stream, stderr=subprocess.STDOUT, timeout=660)
        record['ssh_exit_code'] = proc.returncode
    except Exception as error:
        record['execution_error'] = str(error)
    finally:
        record['status'] = 'FAIL_EXECUTION'
        try:
            record['postflight'] = json.loads(transport.ssh(postflight_command, privileged=True))
            output.mkdir(exist_ok=False)
            retrieve_files(transport.target, remote_output, ['result.json', 'result.json.sha256'], output, OPTIONS)
            result = verified(output/'result.json')
            names = []
            for item in result['records']:
                name = item['capture_filename']
                if Path(name).name != name or '/' in name or '\\' in name or not name.endswith('.npz'):
                    raise ValueError('Unsafe visual capture name')
                names.extend((name, name+'.sha256'))
            if names:
                retrieve_files(transport.target, remote_output, names, output, OPTIONS)
            record['capture_checks'] = verify_captures(output, result)
            record['result_sha256'] = sha(output/'result.json')
            record['library_sha256_after'] = transport.ssh(['sha256sum', library]).split()[0]
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
        write_evidence(final_path, record)
        print('Y2_VISUAL_ENDED '+record['status'], flush=True)


if __name__ == '__main__':
    main()
