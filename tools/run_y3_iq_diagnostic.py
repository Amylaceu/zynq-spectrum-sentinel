"""Capture Y3 diagnostic IQ using an existing audited deployment, without audio."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import shlex

from x2_transport import ROOT, PYTHON, OPTIONS, Transport, sha, verified, write_evidence
from x5_transfer import retrieve_files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, help='Existing isolated board runtime')
    parser.add_argument('--tag', default='y3_iq_diagnostic_r1')
    parser.add_argument('--confirm-configuration-a', action='store_true', required=True)
    parser.add_argument('--sudo-stdin', action='store_true')
    parser.add_argument('--lcd-comparison', action='store_true')
    args = parser.parse_args()
    if not args.tag.replace('_', '').isalnum():
        parser.error('Invalid tag')
    password = sys.stdin.readline().rstrip('\r\n') if args.sudo_stdin else None
    transport = Transport(password)
    stage = args.runtime.rstrip('/')
    bit = stage+'/overlay/sentinel_v2_100m/sentinel_v2_100m.bit'
    output = ROOT/'board/measurements'/args.tag
    receipt = output.with_name(args.tag+'_execution.json')
    log = ROOT/'logs'/('Y3_'+args.tag+'.log')
    if any(p.exists() for p in (output, receipt, log)):
        raise FileExistsError('Preserve diagnostic evidence')
    check = lambda: json.loads(transport.ssh(
        [PYTHON, '-I', stage+'/scripts/y3_postflight.py', '--bit', bit], privileged=True))
    preflight = check()
    if preflight['status'] != 'PASS':
        raise RuntimeError('RF/audio still active')
    script = ROOT/'board/scripts/diagnose_y3_iq.py'
    destination = stage+'/scripts/'+args.tag+'.py'
    transport.ssh(['test', '!', '-e', destination])
    transport.copy(script, transport.target+':'+destination)
    if transport.ssh(['sha256sum', destination]).split()[0] != sha(script):
        raise ValueError('Diagnostic script transfer mismatch')
    remote_out = stage+'/measurements/'+args.tag
    command = [PYTHON, '-I', destination, '--bit', bit, '--out', remote_out,
               '--confirm-configuration-a']
    if args.lcd_comparison:
        command.append('--lcd-comparison')
    record = dict(status='STARTED', started_utc=datetime.now(timezone.utc).isoformat(),
                  configuration='A', RF_TX_requested=False, audio_playback_requested=False,
                  script_sha256=sha(script), preflight=preflight, runtime=stage)
    write_evidence(output.with_name(args.tag+'_start.json'), record)
    try:
        with log.open('xb') as stream:
            proc = subprocess.run(['ssh', *OPTIONS, transport.target,
                                   shlex.join(transport.privileged(command))],
                                  input=(password+'\n').encode() if password else b'',
                                  stdout=stream, stderr=subprocess.STDOUT, timeout=90)
        record['ssh_exit_code'] = proc.returncode
        output.mkdir()
        names = ['result.json', 'result.json.sha256']
        retrieve_files(transport.target, remote_out, names, output, OPTIONS)
        result = verified(output/'result.json')
        retrieve_files(transport.target, remote_out,
                       [c['file'] for c in result.get('captures', [])], output, OPTIONS)
        for capture in result.get('captures', []):
            if sha(output/capture['file']) != capture['sha256']:
                raise ValueError('IQ file hash mismatch')
        record['result_sha256'] = sha(output/'result.json')
        record['postflight'] = check()
        record['status'] = ('PASS_CAPTURE_ONLY' if proc.returncode == 0
                            and result['status'] == 'PASS_CAPTURE_ONLY'
                            and record['postflight']['status'] == 'PASS' else 'FAIL')
    except Exception as error:
        record.update(status='FAIL', error=repr(error))
    finally:
        record['log_sha256'] = sha(log)
        write_evidence(receipt, record)
        print(json.dumps(record), flush=True)
    return 0 if record['status'] == 'PASS_CAPTURE_ONLY' else 1


if __name__ == '__main__':
    raise SystemExit(main())
