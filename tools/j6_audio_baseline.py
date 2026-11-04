"""Compare the previously accepted FM entry without changing RF/DSP algorithms."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'src/ps')]
from x2_transport import Transport, PYTHON
from sentinel.release_support import write_result, sha


def main():
    transport = Transport(sys.stdin.readline().rstrip('\r\n'))
    remote = '/home/xilinx/sentinel/release/j6_audio_r1'
    out = ROOT/'board/measurements/j6_audio_legacy_r1'
    out.mkdir(exist_ok=False)
    command = ['env', 'SENTINEL_RF_LIBRARY='+remote+'/ps/libad9361_pynq/libad9361_pynq.so',
        PYTHON, '-I', remote+'/scripts/run_y3_audio.py', '--bit',
        remote+'/overlay/sentinel_v2_100m/sentinel_v2_100m.bit', '--image', 'sentinel_v2_100m',
        '--out', remote+'/measurements/legacy_audio', '--station-hz', '95800000',
        '--lo-hz', '96050000', '--seconds', '60', '--volume', '-6',
        '--speaker-volume', '0', '--bus-phase', '2', '--stereo-quality-gate', '--ui', 'v3']
    report = dict(source='CURRENT_BOARD_ACCEPTED_LEGACY_ENTRY', seconds=60, antenna='S1',
        human_listening='PENDING', pl_rebuilt=False, tx_requested=False)
    try:
        transport.ssh_lines(command, lambda line: print(line, end='', flush=True), privileged=True, timeout=110)
        report['execution'] = 'COMPLETED'
    except Exception as error:
        report['error'] = repr(error)
    finally:
        transport.copy(transport.target+':'+remote+'/measurements/legacy_audio/result.json', out/'result.json')
        transport.copy(transport.target+':'+remote+'/measurements/legacy_audio/result.json.sha256', out/'result.json.sha256')
        report['result_sha256'] = sha(out/'result.json')
        report['postflight'] = json.loads(transport.ssh([PYTHON, '-I',
            remote+'/scripts/y3_postflight.py', '--bit',
            remote+'/overlay/sentinel_v2_100m/sentinel_v2_100m.bit'], privileged=True))
        write_result(out/'comparison.json', report)


if __name__ == '__main__': main()
