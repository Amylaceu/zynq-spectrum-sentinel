"""Deploy an audited Y3 image for one RF-disabled, three-second speaker test.

Uses a new board directory and immutable PC evidence. A passing digital result
still requires the user's separate, subjective hearing confirmation.
"""
import argparse
import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile

from run_x5_board import INSTALL
from run_y3_board import payload_files
from x2_transport import ROOT, REMOTE, PYTHON, OPTIONS, Transport, sha, verified, write_evidence
from x5_transfer import retrieve_files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3, 4, 5), required=True)
    parser.add_argument('--authorize-extra-attempt', '--authorize-extra-attempt-4',
                        dest='authorize_extra_attempt', action='store_true',
                        help='Explicit user-authorized extra trial; never implicit retry')
    parser.add_argument('--volume', type=float, default=-21,
                        help='Analog output dB, -45..-15 in 1.5 dB steps')
    parser.add_argument('--image', choices=('sentinel_y3', 'sentinel_v2_100m'),
                        default='sentinel_y3')
    parser.add_argument('--implementation-attempt', type=int, choices=(1, 2, 3), default=1)
    parser.add_argument('--preflight-bit', required=True)
    parser.add_argument('--sudo-stdin', action='store_true')
    args = parser.parse_args()
    if args.attempt > 3 and not args.authorize_extra_attempt:
        parser.error('Extra trial requires explicit user authorization')
    sys.path.insert(0, str(ROOT / 'src/ps'))
    from sentinel.audio_y3 import CodecOutputs
    CodecOutputs.volume_code(args.volume)
    password = sys.stdin.readline().rstrip('\r\n') if args.sudo_stdin else None
    if args.sudo_stdin and not password:
        parser.error('Missing sudo credential on stdin')
    tag = ('y3_tone_r%d' if args.image == 'sentinel_y3' else 'y3_v2_tone_r%d') % args.attempt
    output = ROOT / 'board/measurements' / tag
    start = output.with_name(tag + '_start.json')
    execution = output.with_name(tag + '_execution.json')
    log = ROOT / 'logs' / (tag+'_board.log')
    archive = ROOT / 'build' / (tag + '_runtime.tar.gz')
    if any(p.exists() for p in (output, start, execution, log, archive)):
        raise FileExistsError('Preserve previous Y3 tone test')
    files = payload_files(args.implementation_attempt, image=args.image)
    tone = ROOT / 'board/scripts/run_y3_tone.py'
    ast.parse(tone.read_text(encoding='utf-8'), feature_version=(3, 8))
    files['scripts/run_y3_tone.py'] = tone
    manifest = {name: sha(path) for name, path in files.items()}
    with tarfile.open(archive, 'x:gz') as package:
        for name, path in sorted(files.items()):
            package.add(path, arcname=name, recursive=False)
    stage = REMOTE + '/setup/' + tag + '_runtime'
    transport = Transport(password)
    transport.ssh(['test', '!', '-e', stage])
    transport.ssh(['test', '!', '-e', stage + '.tar.gz'])
    transport.copy(archive, transport.target + ':' + stage + '.tar.gz')
    transport.ssh([PYTHON, '-I', '-c', INSTALL], payload=json.dumps(dict(
        root=stage, archive=stage + '.tar.gz', archive_sha256=sha(archive),
        files=manifest)))
    preflight = json.loads(transport.ssh([PYTHON, '-I',
        stage + '/scripts/y3_postflight.py', '--bit', args.preflight_bit],
        privileged=True))
    if preflight['status'] != 'PASS':
        raise RuntimeError('Prior receive/audio program is not stopped')
    bit = stage + '/overlay/' + args.image + '/' + args.image + '.bit'
    remote_output = stage + '/measurements/' + tag
    command = ['timeout', '--signal=TERM', '--kill-after=10s', '25s',
               PYTHON, '-I', stage + '/scripts/run_y3_tone.py',
               '--bit', bit, '--image', args.image, '--load', '--out', remote_output,
               '--volume', str(args.volume)]
    record = dict(status='STARTED', started_at_pc=datetime.now(timezone.utc).isoformat(),
                  extra_attempt_authorized=args.attempt > 3 and args.authorize_extra_attempt,
                  analog_volume_db=args.volume,
                  rf_requested=False, image=args.image, human_hearing='PENDING',
                  output='onboard J36 speaker', command=command,
                  prior_image=preflight, archive_sha256=sha(archive),
                  deployment_sha256=manifest, script_sha256=sha(Path(__file__)))
    write_evidence(start, record)
    try:
        with log.open('xb') as stream:
            process = subprocess.run(['ssh', *OPTIONS, transport.target,
                shlex.join(transport.privileged(command))],
                input=(password + '\n').encode() if password else b'',
                stdout=stream, stderr=subprocess.STDOUT, timeout=35)
        record['ssh_exit_code'] = process.returncode
    except Exception as error:
        record['execution_error'] = repr(error)
    try:
        record['postflight'] = json.loads(transport.ssh([PYTHON, '-I',
            stage + '/scripts/y3_postflight.py', '--bit', bit], privileged=True))
    except Exception as error:
        record['postflight_error'] = repr(error)
    try:
        output.mkdir(exist_ok=False)
        retrieve_files(transport.target, remote_output,
                       ['result.json', 'result.json.sha256'], output, OPTIONS)
        result = verified(output / 'result.json')
        record['result_sha256'] = sha(output / 'result.json')
        after = result.get('audio_after') or {}
        checks = dict(
            duration=result.get('elapsed_s', 0) >= 3,
            frames=result.get('i2s_frames_delta', 0) >= 140000,
            no_underflows=after.get('underflows') == 0,
            played=result.get('status') == 'completed_awaiting_human_hearing',
            audio_pins_off=result.get('audio_control_after') == 0,
            rf_idle=result.get('rf_gpio_after') == 0
                    and result.get('source_control_after') & 1 == 0,
            clean_shutdown=not result.get('safe_stop_errors'),
            same_boot=result.get('boot_id') == preflight['boot_id']
                      == record.get('postflight', {}).get('boot_id'),
            stopped=record.get('postflight', {}).get('status') == 'PASS',
            process_exit=record.get('ssh_exit_code') == 0,
        )
        record['checks'] = checks
        record['status'] = 'PASS_DIGITAL_AWAITING_HUMAN' if all(checks.values()) else 'FAIL'
    except Exception as error:
        record.update(status='FAIL', retrieval_error=repr(error))
    write_evidence(execution, record)
    print(json.dumps(dict(status=record['status'], checks=record.get('checks'),
                          execution=str(execution), board_log=str(log)), indent=2))
    if record['status'] != 'PASS_DIGITAL_AWAITING_HUMAN':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
