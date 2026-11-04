"""Bounded comparison with the accepted legacy listener; no TX or PL reload."""
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
    output = ROOT/'board/measurements/j8_fm_recovery_r2'
    output.mkdir(exist_ok=False)
    remote_output = remote+'/measurements/j8_legacy_compare_r2'
    report = dict(status='RUNNING', frequency_hz=95800000,
                  human_listening='PENDING', recording=False, tx_requested=False,
                  pl_rebuilt=False, bitstream_download=False)
    try:
        loaded = transport.ssh([PYTHON, '-c', "import os; os.environ['XILINX_XRT']='/usr'; from pynq import PL; print(PL.bitfile_name)"], privileged=True).strip()
        if not (loaded.startswith('/home/xilinx/sentinel/release/') and
                loaded.endswith('/overlay/sentinel_v2_100m/sentinel_v2_100m.bit')):
            raise RuntimeError('Unexpected loaded overlay path')
        report['bit_sha256'] = transport.ssh(['sha256sum', loaded]).split()[0]
        if report['bit_sha256'] != sha(ROOT/'board/overlay/sentinel_v2_100m/sentinel_v2_100m.bit'):
            raise RuntimeError('Frozen overlay digest mismatch')
        report['preflight'] = json.loads(transport.ssh([PYTHON, '-I', remote+'/scripts/y3_postflight.py', '--bit', loaded], privileged=True))
        if report['preflight']['status'] != 'PASS':
            raise RuntimeError('Stopped preflight required')
        command = ['env', 'SENTINEL_RF_LIBRARY='+remote+'/ps/libad9361_pynq/libad9361_pynq.so',
            PYTHON, '-I', remote+'/scripts/run_y3_audio.py', '--bit', loaded,
            '--image', 'sentinel_v2_100m', '--out', remote_output,
            '--station-hz', '95800000', '--lo-hz', '96050000', '--seconds', '60',
            '--volume', '-6', '--speaker-volume', '0', '--bus-phase', '2',
            '--stereo-quality-gate', '--ui', 'v3']
        print('LEGACY_CHECK_STARTING', flush=True)
        transport.ssh_lines(command, lambda line: print(line, end='', flush=True), privileged=True, timeout=120)
        report['status'] = 'EXECUTION_COMPLETED_LISTENING_PENDING'
    except Exception as error:
        report.update(status='FAIL', error=repr(error))
        print('LEGACY_FAILED', repr(error), flush=True)
    finally:
        for name in ('result.json', 'result.json.sha256'):
            try:
                transport.copy(transport.target+':'+remote_output+'/'+name, output/name)
            except Exception as error:
                report.setdefault('retrieval_errors', []).append(repr(error))
        if (output/'result.json').exists():
            report['result_sha256'] = sha(output/'result.json')
        if 'loaded' in locals():
            try:
                report['postflight'] = json.loads(transport.ssh([PYTHON, '-I', remote+'/scripts/y3_postflight.py', '--bit', loaded], privileged=True))
            except Exception as error:
                report.update(status='FAIL_STOP_UNCONFIRMED', stop_error=repr(error))
        write_result(output/'comparison.json', report)
        print('LEGACY_FINISHED', report['status'], flush=True)


if __name__ == '__main__':
    main()
