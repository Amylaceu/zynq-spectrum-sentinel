"""Receive-only LCD twin validation on the unchanged 100 MHz release.

No audio or TX commands. Credentials accepted on stdin only. Each run has a
new directory; stop and independent readback also run on error paths.
"""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tools'), str(ROOT/'src/ps'), str(ROOT/'tools/host')]
import numpy as np
from g3_validate import launch, completed
from fetch_release_evidence import fetch
from run_x1_board import write_evidence
from x2_transport import Transport, PYTHON, REMOTE
from sentinel.app.hostlink_protocol import Decoder, encode
from sentinel.display_twin import decompress_exact, UI_BYTES


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sudo-stdin', action='store_true', required=True)
    p.add_argument('--name', default='g4a_board_r1')
    p.add_argument('--seconds', type=int, default=150)
    a = p.parse_args()
    if a.name not in ('g4a_board_r1', 'g4a_board_r2', 'g4a_board_r3') or not 90 <= a.seconds <= 600:
        p.error('Bounded G4a test only')
    t = Transport(password=sys.stdin.readline().rstrip('\r\n'))
    output = ROOT/'board/measurements'/a.name
    output.mkdir(exist_ok=False)
    root = REMOTE+'/release/v2'
    result = dict(status='STARTED', configuration='A', tx_requested=False,
                  scope='G4a short functionality/readback/click measurement; not G4b 30-minute acceptance')
    process = None
    try:
        launch(t, a.name, a.seconds+90, True)
        address = t.target.rsplit('@', 1)[-1]
        deadline = time.monotonic()+90
        while True:
            try:
                client = socket.create_connection((address, 9000), timeout=2)
                break
            except OSError:
                if time.monotonic() > deadline: raise
                time.sleep(1)
        command = [sys.executable, str(ROOT/'tools/host/run_host.py'), '--connect', address,
            '--record', str(output/'live_A_twin.zsr'), '--auto-exit', str(a.seconds),
            '--evidence', str(output/'gui_metrics.json'), '--screenshot-out', str(output/'twin_live.png')]
        process = subprocess.Popen(command, cwd=ROOT)
        print('TWIN_GUI_STARTED', process.pid, flush=True)
        decoder, seq = Decoder(), 100000
        first = time.monotonic()
        due = first+5
        pending, timings, ui_verified, counts, replies = {}, [], {}, {}, []
        client.settimeout(.2)
        with client, (output/'wire.jsonl').open('x', encoding='utf-8') as wire:
            while time.monotonic()-first < a.seconds-5:
                now = time.monotonic()
                if now >= due and seq < 100020:
                    seq += 1
                    x = (570, 650, 730)[(seq-100001) % 3]
                    header = dict(type='command', seq=seq, t_mono=now, len=0,
                                  command='click', args=dict(x=x, y=12))
                    client.sendall(encode(header))
                    pending[seq] = now
                    due = now+1
                try: data = client.recv(65536)
                except socket.timeout: continue
                if not data: raise ConnectionError('Board disconnected during twin test')
                for header, payload in decoder.feed(data):
                    received = time.monotonic()
                    kind = header['type']
                    counts[kind] = counts.get(kind, 0)+1
                    wire.write(json.dumps(dict(header=header, host_received_mono=received,
                        payload_sha256=hashlib.sha256(payload).hexdigest()), allow_nan=False)+'\n')
                    if kind == 'reply': replies.append(header)
                    if kind != 'ui_frame': continue
                    request = header.get('request')
                    if request and request[1] in pending:
                        timings.append(1000*(received-pending.pop(request[1])))
                    if header.get('readback_verified'):
                        raw = decompress_exact(payload, UI_BYTES)
                        digest = hashlib.sha256(raw).hexdigest()
                        if digest != header['sha256'] or digest != header['readback_sha256']:
                            raise ValueError('Received UI readback digest mismatch')
                        ui_verified[str(header['epoch'])] = digest
        process.wait(timeout=40)
        if process.returncode: raise RuntimeError('GUI exited nonzero')
        print(t.ssh(['sh', root+'/scripts/sentinel.sh', 'stop'], privileged=True), flush=True)
        tag = completed(t, a.name, 90)
        fetch(tag, 'monitor', output/'board_raw')
        # Independently compare wire digests to the fetched actual BRAM words.
        files = list((output/'board_raw').rglob('epoch_*.u32'))
        verified = []
        for path in files:
            epoch = str(int(path.stem.split('_')[1]))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if epoch in ui_verified:
                if digest != ui_verified[epoch]: raise ValueError('Fetched BRAM differs from received UI')
                verified.append(epoch)
        gui = json.loads((output/'gui_metrics.json').read_text())
        result.update(status='MEASURED', tag=tag, counts=counts, click_ms=timings,
            click_median_ms=float(np.median(timings)) if timings else None,
            click_p95_ms=float(np.percentile(timings,95)) if timings else None,
            click_scope='Host send through board owner, LCD APPLIED and matching ui_frame receive; no optical scanout timing',
            click_completed=len(timings), click_pending=list(pending),
            verified_bram_epochs=verified, gui=gui, command_rejections=[r for r in replies if not r.get('ok')],
            threshold_twin='UNAVAILABLE_FROZEN_IMAGE_HAS_NO_TRACE_READBACK',
            pl_frame_mapping='SAMPLED_POWER_REFERENCE_NOT_EXACT_LCD_FFT_FRAME')
    except BaseException as error:
        result.update(status='FAIL', error=repr(error))
        raise
    finally:
        if process is not None and process.poll() is None:
            # Close only the child started by this validator.
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)
        try:
            result['stop'] = t.ssh(['sh', root+'/scripts/sentinel.sh', 'stop'], privileged=True)
            result['postflight'] = json.loads(t.ssh([PYTHON, '-I', root+'/scripts/y3_postflight.py',
                '--bit', root+'/overlay/sentinel_v2_100m/sentinel_v2_100m.bit'], privileged=True))
        except BaseException as error:
            result['cleanup_error'] = repr(error)
        write_evidence(output/'validation.json', result)
    print('G4A_MEASUREMENT_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
