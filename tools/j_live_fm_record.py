"""Capture one current five-second FM recording and optionally show its player."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import uuid

from x2_transport import Transport, REMOTE, PYTHON
from run_x1_board import ROOT, OPTIONS, sha, write_evidence


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--antenna-fm-confirmed', action='store_true', required=True)
    p.add_argument('--show-player', action='store_true')
    p.add_argument('--listen-during-recording', action='store_true')
    p.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    p.add_argument('--sudo-stdin', action='store_true', required=True)
    args = p.parse_args()
    password = sys.stdin.readline().rstrip('\r\n')
    if not password:
        p.error('Missing credential on stdin')
    t = Transport(password)
    tag = 'j_live_fm_record_r%d' % args.attempt
    session_id = str(uuid.uuid4())
    out = ROOT/'board/measurements'/tag
    out.mkdir(exist_ok=False)
    from pathlib import PurePosixPath
    from x2_transport import verified
    preflight = verified(ROOT/'board/measurements/j_live_hotspot_preflight_r1.json')
    bit = preflight['loaded_bundle']['bit']
    root = str(PurePosixPath(bit).parents[2])
    if not root.startswith(REMOTE+'/release/') or not bit.endswith('/sentinel_v2_100m.bit'):
        raise ValueError('Unexpected accepted bundle location')
    stage = REMOTE+'/setup/'+tag
    record = dict(status='STARTED', antenna='RX1A_FM_20_512', session_id=session_id,
                  host_utc=datetime.now(timezone.utc).isoformat(), rf_tx_requested=False,
                  pl_rebuilt=False, bitstream_download=False)
    def stopped():
        return json.loads(t.ssh([PYTHON, '-I', root+'/scripts/y3_postflight.py',
                       '--bit', bit], privileged=True))
    try:
        record['bundle_root'] = root
        record['bit_sha256'] = preflight['loaded_bundle']['sha256']
        record['preflight'] = stopped()
        if record['preflight']['status'] != 'PASS':
            raise RuntimeError('Stopped preflight required')
        t.ssh(['mkdir', stage])  # unique, never overwrite earlier evidence
        source = ROOT/'board/scripts/run_j_live_fm_record.py'
        t.copy(source, t.target+':'+stage+'/run.py')
        record['script_sha256'] = sha(source)
        if t.ssh(['sha256sum', stage+'/run.py']).split()[0] != sha(source):
            raise RuntimeError('Uploaded script mismatch')
        command = [PYTHON, '-I', stage+'/run.py', '--root', root,
                   '--out', stage+'/raw', '--antenna-fm-confirmed', '--session-id', session_id]
        if args.listen_during_recording:
            command.append('--listen-during-recording')
        with (out/'board.log').open('x', encoding='utf-8') as log:
            def on_line(line):
                log.write(line)
                log.flush()
                print(line, end='', flush=True)
            try:
                t.ssh_lines(command, on_line, privileged=True, timeout=230)
            except Exception as error:
                record['execution_error'] = repr(error)
        subprocess.run(['scp', *OPTIONS, '-r', t.target+':'+stage+'/raw', str(out/'raw')],
                       check=True, capture_output=True, timeout=180)
        files = {}
        for sidecar in (out/'raw').rglob('*.sha256'):
            path = Path(str(sidecar)[:-7])
            if not path.is_file() or sha(path) != sidecar.read_text().split()[0]:
                raise RuntimeError('Retrieved evidence mismatch')
            files[path.name] = sha(path)
        if len(files) != 2 or 'result.json' not in files or 'current_adc_iq.i16' not in files:
            raise RuntimeError('Need current IQ and signed result')
        record['files_sha256'] = files
        result = json.loads((out/'raw/result.json').read_text())
        record['status'] = result['status'] if 'execution_error' not in record else 'FAIL'
    except Exception as error:
        record.update(status='FAIL', error=repr(error))
    finally:
        try:
            record['postflight'] = stopped()
            if record['postflight']['status'] != 'PASS':
                record['status'] = 'FAIL'
        except Exception as error:
            record.update(status='FAIL', postflight_error=repr(error))
        write_evidence(out/'validation.json', record)
    print('J_LIVE_FM_RECORD_FINISHED', record['status'], flush=True)
    if record['status'] != 'PASS_FINITE_RECORDING':
        return 1
    from current_fm_audio import decode
    wav, audio = decode(out, session_id)
    print(json.dumps(audio), flush=True)
    if audio['status'] != 'READY_FOR_LISTENING':
        return 2
    if args.show_player:
        sys.path.insert(0, str(ROOT/'tools/host'))
        from PySide6 import QtWidgets
        from sentinel_host.current_audio import CurrentAudioDialog
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        window = CurrentAudioDialog(out, session_id)
        window.show()
        window.raise_()
        return app.exec()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
