"""Run one confirmed receive-only panorama and fetch immutable raw evidence."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src/ps'))
from x2_transport import Transport, REMOTE, PYTHON
from run_x1_board import write_evidence, sha, OPTIONS


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--group', choices=('A', 'D'), required=True)
    p.add_argument('--antenna-confirmed', action='store_true', required=True)
    p.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    p.add_argument('--limit', type=int)
    p.add_argument('--profile', choices=('legacy', 'fast'), default='legacy')
    p.add_argument('--keep-iq', action='store_true')
    p.add_argument('--sudo-stdin', action='store_true', required=True)
    args = p.parse_args()
    from sentinel.panorama_capture import validate_request
    validate_request(args.group, args.antenna_confirmed, args.limit, args.profile)
    password = sys.stdin.readline().rstrip('\r\n')
    if not password:
        p.error('Credential missing on stdin')
    t = Transport(password=password)
    name = ('h1_' if args.profile == 'fast' else 'f4_')+args.group.lower()+'_scan_r%d' % args.attempt
    output = ROOT/'board/measurements'/name
    output.mkdir(exist_ok=False)
    root = REMOTE+'/release/v2'
    remote_output = root+'/measurements/'+name
    result = dict(status='STARTED', group=args.group, host_utc=datetime.now(timezone.utc).isoformat(),
                  pl_rebuilt=False, antenna_confirmed=True)
    try:
        result['preflight'] = json.loads(t.ssh([PYTHON, '-I', root+'/scripts/y3_postflight.py',
            '--bit', root+'/overlay/sentinel_v2_100m/sentinel_v2_100m.bit'], privileged=True))
        if result['preflight'].get('status') != 'PASS':
            raise RuntimeError('Stopped preflight required')
        command = [PYTHON, '-I', root+'/scripts/run_f4_panorama.py', '--group', args.group,
                   '--antenna-confirmed', '--output', remote_output, '--profile', args.profile]
        if args.keep_iq:
            command += ['--keep-iq']
        if args.limit is not None:
            command += ['--limit', str(args.limit)]
        try:
            with (output/'board.log').open('x', encoding='utf-8') as log, \
                    (output/'pano_tiles.jsonl').open('x', encoding='utf-8') as progress:
                def on_line(line):
                    log.write(line)
                    log.flush()
                    if line.startswith('{'):
                        packet = json.loads(line)
                        if packet.get('type') == 'pano_tile':
                            progress.write(line)
                            progress.flush()
                t.ssh_lines(command, on_line, privileged=True, timeout=700)
            from sentinel.panorama_capture import seal
            seal(output/'pano_tiles.jsonl')
        except Exception as error:
            result['execution_error'] = repr(error)
        # Never infer success from the transport return code; fetch result/sidecars.
        subprocess.run(['scp', *OPTIONS, '-r', t.target+':'+remote_output, str(output/'raw')],
                       check=True, timeout=180, capture_output=True)
        files = {}
        for sidecar in (output/'raw').rglob('*.sha256'):
            path = Path(str(sidecar)[:-7])
            if not path.is_file() or sha(path) != sidecar.read_text().split()[0]:
                raise RuntimeError('Fetched evidence digest mismatch: '+str(path))
            files[path.relative_to(output/'raw').as_posix()] = sha(path)
        result['files_sha256'] = files
        record = json.loads((output/'raw/result.json').read_text())
        result['scan'] = record
        result['status'] = record['status']
    except Exception as error:
        result.update(status='FAIL', error=repr(error))
    finally:
        try:
            result['postflight'] = json.loads(t.ssh([PYTHON, '-I', root+'/scripts/y3_postflight.py',
                '--bit', root+'/overlay/sentinel_v2_100m/sentinel_v2_100m.bit'], privileged=True))
            if result['postflight']['status'] != 'PASS':
                result['status'] = 'FAIL'
        except Exception as error:
            result.update(status='FAIL', postflight_error=repr(error))
        write_evidence(output/'validation.json', result)
    print('F4_COMPLETE', result['status'], flush=True)
    if result['status'] != 'PASS_SNAPSHOT_SCAN':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
