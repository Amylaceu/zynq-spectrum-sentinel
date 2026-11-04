"""Bounded receive-only user-requested speaker volume check using the accepted I1 candidate.

No deployment or TX command is performed. A speaker-gain candidate explicitly
reloads the same frozen bitstream for PYNQ path ownership. The caller must
confirm S1 hardware. Credentials are read from stdin and never persisted.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import subprocess
import sys

from run_x1_board import ROOT, OPTIONS, sha, write_evidence
from run_y3_board import evaluate
from x2_transport import Transport, REMOTE, PYTHON


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--antenna', choices=('S1',), required=True)
    parser.add_argument('--antenna-confirmed', action='store_true', required=True)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--volume', type=int, choices=(-9, -6), default=-9)
    parser.add_argument('--speaker-volume', type=int, choices=(-3, 0))
    parser.add_argument('--sudo-stdin', action='store_true', required=True)
    args = parser.parse_args()
    password = sys.stdin.readline().rstrip('\r\n')
    if not password:
        parser.error('Missing credential on stdin')
    transport = Transport(password=password)
    root = REMOTE+'/release/'+('audio_volume_r1' if args.speaker_volume is not None else 'i1_r3')
    bit = root+'/overlay/sentinel_v2_100m/sentinel_v2_100m.bit'
    tag = 'i1_volume_m%d_r%d' % (-args.volume, args.attempt)
    if args.speaker_volume is not None:
        tag = 'i1_speaker_%ddB_r%d' % (args.speaker_volume, args.attempt)
    output = ROOT/'board/measurements'/tag
    output.mkdir(exist_ok=False)
    remote_output = root+'/measurements/'+tag
    record = dict(status='STARTED', host_utc=datetime.now(timezone.utc).isoformat(),
                  antenna=args.antenna, antenna_confirmed=True,
                  physical_tx1a='2.4GHz antenna attached; TX not requested',
                  pl_rebuilt=False, bitstream_download=args.speaker_volume is not None, human_listening='PENDING',
                  speaker_volume_db=args.speaker_volume,
                  requested_volume_db=args.volume, scope='60 s user-requested continuous FM; existing audio worker, not a fourth I1 scene-switch attempt')

    def stopped():
        loaded = transport.ssh([PYTHON, '-c', "import os; os.environ['XILINX_XRT']='/usr'; from pynq import PL; print(PL.bitfile_name)"], privileged=True).strip()
        if not (loaded.startswith(REMOTE+'/release/') and loaded.endswith('/overlay/sentinel_v2_100m/sentinel_v2_100m.bit')):
            raise RuntimeError('Unexpected loaded image path: '+loaded)
        return json.loads(transport.ssh([PYTHON, '-I', root+'/scripts/y3_postflight.py',
                                         '--bit', loaded], privileged=True))

    try:
        accepted = ROOT/'board/measurements/i1_board_r3/acceptance.json'
        if sha(accepted) != Path(str(accepted)+'.sha256').read_text().split()[0]:
            raise RuntimeError('I1 evidence digest mismatch')
        previous = json.loads(accepted.read_text())
        if previous.get('status') != 'PARTIAL_RECEIVE_SCENES_PASS' or previous.get('postflight', {}).get('status') != 'PASS':
            raise RuntimeError('I1 accepted and stopped candidate required')
        record['preflight'] = stopped()
        if record['preflight']['status'] != 'PASS':
            raise RuntimeError('Stopped preflight required')
        # Validate the installed manifest/library, without initialization.
        transport.ssh([PYTHON, '-I', root+'/scripts/release_entry.py', 'verify'])
        paths = {root+'/scripts/run_y3_audio.py': ROOT/'board/scripts/run_y3_audio.py',
                 bit: ROOT/'board/overlay/sentinel_v2_100m/sentinel_v2_100m.bit'}
        digests = transport.ssh(['sha256sum', *paths])
        for line in digests.splitlines():
            digest, name = line.split(maxsplit=1)
            if digest != sha(paths[name]):
                raise RuntimeError('Installed file differs: '+name)
        record['installed_files_sha256'] = {name: sha(path) for name, path in paths.items()}
        library = root+'/ps/libad9361_pynq/libad9361_pynq.so'
        digest = transport.ssh(['sha256sum', library]).split()[0]
        if digest != 'b329018314e6ecc9c0b11440b0d5449d9670fda7b5d37deabdc55c4731616e83':
            raise RuntimeError('Frozen receive library differs')
        record['receive_library_sha256'] = digest
        command = ['env', 'SENTINEL_RF_LIBRARY='+library, PYTHON, '-I',
                   root+'/scripts/run_y3_audio.py', '--bit', bit,
                   '--image', 'sentinel_v2_100m', '--out', remote_output,
                   '--station-hz', '95800000', '--lo-hz', '96050000',
                   '--seconds', '60', '--volume', str(args.volume), '--bus-phase', '2',
                   '--stereo-quality-gate', '--ui', 'v3']
        if args.speaker_volume is not None:
            command += ['--speaker-volume', str(args.speaker_volume), '--load']
        with (output/'board.log').open('x', encoding='utf-8') as log:
            def on_line(line):
                log.write(line)
                log.flush()
                print(line, end='', flush=True)
            try:
                transport.ssh_lines(command, on_line, privileged=True, timeout=140)
            except Exception as error:
                record['execution_error'] = repr(error)
        subprocess.run(['scp', *OPTIONS, '-r', transport.target+':'+remote_output,
                        str(output/'raw')], check=True, timeout=90, capture_output=True)
        files = {}
        for sidecar in (output/'raw').rglob('*.sha256'):
            path = Path(str(sidecar)[:-7])
            if not path.is_file() or sha(path) != sidecar.read_text().split()[0]:
                raise RuntimeError('Retrieved evidence digest mismatch: '+str(path))
            files[path.relative_to(output/'raw').as_posix()] = sha(path)
        if 'result.json' not in files:
            raise RuntimeError('Missing signed result')
        record['files_sha256'] = files
        result = json.loads((output/'raw/result.json').read_text())
        # Legacy worker records TX1A as disconnected. Keep raw evidence intact
        # and explicitly describe the actual connector above, without rewriting it.
        record['legacy_metadata_note'] = 'raw tx1a field is historical A wording; actual hardware recorded above'
        record['postflight'] = stopped()
        record['checks'] = evaluate(result, 60, record['preflight'], record['postflight'])
        pilots = [v['pilot_prominence_db'] for v in result.get('quality_samples', [])]
        record['pilot_db'] = dict(count=len(pilots), minimum=min(pilots) if pilots else None,
                                 median=statistics.median(pilots) if pilots else None)
        record['checks']['pilot_min_20db'] = bool(pilots) and min(pilots) >= 20
        record['audible_seconds'] = result.get('audible_seconds')
        record['status'] = 'PASS_AUTOMATED_AWAITING_LISTENING' if (
            all(record['checks'].values()) and 'execution_error' not in record) else 'FAIL'
    except Exception as error:
        record.update(status='FAIL', error=repr(error))
    finally:
        try:
            record['postflight'] = stopped()
            if record['postflight'].get('status') != 'PASS':
                record['status'] = 'FAIL'
        except Exception as error:
            record.update(status='FAIL', postflight_error=repr(error))
        write_evidence(output/'validation.json', record)
    print(json.dumps(record, indent=2), flush=True)
    return 0 if record['status'] == 'PASS_AUTOMATED_AWAITING_LISTENING' else 1


if __name__ == '__main__':
    raise SystemExit(main())
