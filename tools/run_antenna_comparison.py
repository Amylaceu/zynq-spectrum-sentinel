"""One confirmed antenna, one 120-second receive-only comparison window.

Reuse the frozen X1 monitor unchanged. No transmit or antenna switching.
Supply sudo credentials via stdin, never command-line or saved files.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
from zoneinfo import ZoneInfo

from deploy_x1 import board_identity
from run_x1_board import OPTIONS, PYTHON, REMOTE, ROOT, sha, write_evidence

ANTENNAS = {'long': 'ANT-1: thick/long 20-512MHz, short feedline',
            'short': 'ANT-2: thin/short 20-512MHz, long feedline',
            'third': 'Third user-connected antenna; model and frequency range not provided',
            'new': 'New user-found antenna, user-reported same frequency band; model not provided'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--antenna', choices=ANTENNAS, required=True)
    parser.add_argument('--run-id', default='r1',
                        help='Unique evidence suffix; previous runs are never overwritten')
    parser.add_argument('--confirm-rx1a-tx-empty', action='store_true', required=True)
    parser.add_argument('--sudo-stdin', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,47}', args.run_id):
        parser.error('run-id must contain lowercase ASCII letters, digits, underscores or hyphens')
    tag = 'antenna_compare_%s_%s' % (args.antenna, args.run_id)
    output = ROOT / ('board/measurements/' + tag + '.json')
    receipt = output.with_name(tag + '_execution.json')
    log = ROOT / ('logs/X1_' + tag + '.log')
    for path in (output, receipt, log):
        if path.exists() or Path(str(path) + '.sha256').exists():
            parser.error('Preserve existing experiment: ' + str(path))
    frozen = json.loads((ROOT / 'docs/x1_software_predeployment_r3.json').read_text())
    for relative, digest in frozen['source_sha256'].items():
        if sha(ROOT / relative) != digest:
            raise ValueError('Frozen software changed: ' + relative)
    password = sys.stdin.readline().rstrip('\r\n') if args.sudo_stdin else None
    if args.sudo_stdin and not password:
        parser.error('Missing credential on stdin')
    target = board_identity()

    def ssh(command, privileged=False):
        prefix = ['sudo', '-S', '-p', ''] if args.sudo_stdin else ['sudo', '-n']
        remote = shlex.join(prefix + command) if privileged else command
        response = subprocess.run(['ssh', *OPTIONS, target, remote],
                                  input=password + '\n' if privileged and password else None,
                                  capture_output=True, text=True, timeout=40)
        if response.returncode:
            raise RuntimeError('SSH check failed: ' + response.stderr[-800:])
        return response.stdout

    boot = ssh('cat /proc/sys/kernel/random/boot_id').strip()
    postflight = [PYTHON, '-I', REMOTE + '/scripts/x1_postflight.py']
    before = json.loads(ssh(postflight, privileged=True))
    if before['status'] != 'PASS' or before['boot_id'] != boot:
        raise ValueError('Receiver must be stopped before changing/test antenna')
    source = ROOT / 'src/ps/sentinel/app/monitor_x1.py'
    remote_digest = ssh('sha256sum ' + REMOTE + '/ps/sentinel/app/monitor_x1.py').split()[0]
    if sha(source) != remote_digest:
        raise ValueError('Board monitor differs from frozen source')
    remote_output = REMOTE + '/measurements/' + tag + '.json'
    if ssh('test ! -e ' + remote_output + ' && echo NEW_OUTPUT').strip() != 'NEW_OUTPUT':
        raise FileExistsError(remote_output)
    command = [PYTHON, '-I', REMOTE + '/scripts/run_x1_monitor.py',
               '--bit', REMOTE + '/overlay/sentinel_v1b/sentinel_v1b.bit',
               '--out', remote_output, '--lo', '96400000', '--seconds', '120',
               '--average-shift', '3', '--min-width', '2', '--merge-gap', '6',
               '--alpha', '1974', '--capture-power']
    sudo = ['sudo', '-S', '-p', ''] if args.sudo_stdin else ['sudo', '-n']
    record = {'antenna': args.antenna, 'antenna_description': ANTENNAS[args.antenna],
              'user_confirmed_rx1a_tx_empty': True, 'preflight': before,
              'started_at_pc': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
              'command': command, 'boot_id_before': boot,
              'scope': 'Additional user-authorized antenna comparison; not an X1 fourth tuning round',
              'placement_protocol': 'Same marked base location, vertical orientation and supporting surface',
              'monitor_sha256': remote_digest}
    record.update(run_id=args.run_id,
                  controller_sha256=sha(Path(__file__).resolve()))
    if args.antenna == 'third':
        record.update(antenna_identification_status='NOT_PROVIDED',
                      same_placement_explicitly_confirmed=False,
                      connection_confirmation='User reports third antenna connected and explicitly requests receive test')
    print('START ' + tag + ' LO=96.4MHz, target=95.8MHz, 120s, receive only', flush=True)
    with log.open('xb') as stream:
        process = subprocess.Popen(['ssh', *OPTIONS, target, shlex.join(sudo + command)],
                                   stdin=subprocess.PIPE, stdout=stream, stderr=subprocess.STDOUT)
        process.communicate((password + '\n').encode() if password else b'')
    record.update(ssh_exit_code=process.returncode,
                  ended_at_pc=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
                  log=log.relative_to(ROOT).as_posix(), log_sha256=sha(log))
    try:
        after = json.loads(ssh(postflight, privileged=True))
        record['postflight'] = after
        subprocess.run(['scp', *OPTIONS, target + ':' + remote_output, str(output)],
                       check=True, timeout=40)
        digest = sha(output)
        Path(str(output) + '.sha256').write_text(digest + '  ' + output.name + '\n', encoding='ascii')
        data = json.loads(output.read_text())
        record.update(result_sha256=digest, result_status=data['status'])
        record['status'] = 'PASS_EXECUTION' if (process.returncode == 0 and data['status'] == 'completed'
            and data['boot_id'] == boot and after['boot_id'] == boot and after['status'] == 'PASS') else 'FAIL_EXECUTION'
    except Exception as error:
        record.update(status='FAIL_POSTFLIGHT_OR_RETRIEVAL', error=str(error))
    password = None
    write_evidence(receipt, record)
    print(json.dumps(record, indent=2), flush=True)
    return 0 if record['status'] == 'PASS_EXECUTION' else 1


if __name__ == '__main__':
    raise SystemExit(main())
