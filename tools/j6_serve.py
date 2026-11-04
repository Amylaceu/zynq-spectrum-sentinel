"""Deploy or serve a bounded, isolated J6 receive-only software candidate."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'src/ps')]
from x2_transport import Transport, PYTHON
from sentinel.release_support import write_result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', choices=('j6_dma_r1', 'j6_audio_r1', 'j6_audio_r2', 'j6_audio_r3', 'j7_r1', 'j7_r2', 'j7_r3', 'j7_final', 'j7_rec3_r1', 'j8_r1', 'j8_r2', 'j8_r3', 'j8_final'), required=True)
    parser.add_argument('--deploy', action='store_true')
    parser.add_argument('--sudo-stdin', action='store_true')
    parser.add_argument('--session', required=True)
    parser.add_argument('--seconds', type=int, default=1800, choices=range(1, 3601))
    parser.add_argument('--panorama-settle-ms', type=int, choices=(50, 150), default=50)
    args = parser.parse_args()
    if not args.session.replace('_', '').isalnum(): parser.error('Simple session name required')
    password = sys.stdin.readline().rstrip('\r\n') if args.sudo_stdin else None
    transport = Transport(password)
    remote = '/home/xilinx/sentinel/release/'+args.candidate
    if args.deploy:
        from release_board import build, deploy
        archive = build(ROOT/'build'/args.candidate)
        print(json.dumps(deploy(archive, password=password, candidate=args.candidate)), flush=True)
    try:
        transport.ssh_lines([PYTHON, '-I', remote+'/scripts/serve_features_j6.py',
            '--out', remote+'/measurements/'+args.session, '--hostlink-bind', '192.168.2.99',
            '--seconds', str(args.seconds), '--panorama-settle-ms', str(args.panorama_settle_ms)], lambda line: print(line, end='', flush=True),
            privileged=True, timeout=args.seconds+90)
    finally:
        output = ROOT/'board/measurements'/args.candidate/args.session
        output.mkdir(parents=True, exist_ok=True)
        transport.copy(transport.target+':'+remote+'/measurements/'+args.session+'/result.json', output/'result.json')
        transport.copy(transport.target+':'+remote+'/measurements/'+args.session+'/result.json.sha256', output/'result.json.sha256')
        write_result(output/'postflight.json', json.loads(transport.ssh([PYTHON, '-I',
            remote+'/scripts/y3_postflight.py', '--bit',
            remote+'/overlay/sentinel_v2_100m/sentinel_v2_100m.bit'], privileged=True)))


if __name__ == '__main__': main()
