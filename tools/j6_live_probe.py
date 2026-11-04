"""Bounded J6 target/audio diagnosis over the receive-only control protocol."""
import argparse
import json
from pathlib import Path
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src/ps'))
from sentinel.app.hostlink_protocol import Decoder, encode
from sentinel.release_support import write_result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--audio-seconds', type=int, default=30, choices=range(1, 61))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(source='CURRENT_BOARD', replies=[], telemetry=[], target_selection=None)
    decoder = Decoder(); seq = 0; packets = []; targets = []
    with socket.create_connection(('192.168.2.99', 9000), timeout=5) as connection:
        connection.settimeout(.2)
        def collect(seconds, request=None):
            deadline = time.monotonic()+seconds
            while time.monotonic() < deadline:
                try: data = connection.recv(65536)
                except socket.timeout: continue
                if not data: raise ConnectionError('Board disconnected')
                for header, _ in decoder.feed(data):
                    packets.append(header)
                    if header['type'] == 'telemetry': report['telemetry'].append(header)
                    if header['type'] == 'detections': targets[:] = header['targets']
                    if header['type'] in ('reply', 'error'):
                        report['replies'].append(header)
                        if header.get('request_seq') == request: return header
            if request is not None: raise TimeoutError('No matching reply')
        def command(name, **values):
            nonlocal seq
            seq += 1
            connection.sendall(encode(dict(type='command', seq=seq, len=0,
                t_mono=time.monotonic(), command=name, args=values)))
            value = collect(12, seq)
            print(json.dumps(value, ensure_ascii=True), flush=True)
            return value
        def feature(key, action='start'):
            return command('feature', id=key, action=action, mode='CA', alpha=1974)
        try:
            command('stop')
            report['f7'] = feature('F7')
            collect(.8)
            if targets:
                report['target_requested'] = targets[0]
                report['target_selection'] = command('select_target', key=targets[0]['key'])
            feature('F7', 'stop')
            report['f8'] = feature('F8')
            if report['f8'].get('feature', {}).get('status') != 'READY':
                report['status'] = 'FAIL_AUDIO_NOT_READY'
                return
            print('AUDIO_LISTENING %d seconds' % args.audio_seconds, flush=True)
            collect(args.audio_seconds)
        finally:
            report['final_stop'] = feature('F8', 'stop')
            report['final_readback'] = command('get_status')
            write_result(args.output/'result.json', report)


if __name__ == '__main__': main()
