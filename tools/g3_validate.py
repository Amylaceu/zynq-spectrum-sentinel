"""G3 receive-only baseline/service validation; credentials only on stdin.

Uses installed frozen release. Run in background with logs/G3*.log redirection.
Ten reconnect cycles disconnect the PC application for >=30s each; this is not
a physical cable-unplug or calibrated PL-to-PC latency test.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src/ps'), str(ROOT/'tools')]
from sentinel.app.hostlink_protocol import Decoder, encode
from run_x1_board import write_evidence
from x2_transport import Transport, REMOTE, PYTHON
from fetch_release_evidence import fetch


def launch(transport, name, seconds, hostlink):
    root = REMOTE+'/release/v2'
    command = ['sh', root+'/scripts/sentinel.sh', 'monitor', '--ui', 'v3', '--seconds', str(seconds)]
    if hostlink:
        command.append('--hostlink')
    # All values go through JSON to a fixed Python script, never shell interpolation.
    script = '''import subprocess,json,pathlib
p=json.loads(%r)
if pathlib.Path('/run/zss_release_v2.json').exists():raise RuntimeError('Release already running')
with open(p['log'],'x') as log:
 child=subprocess.Popen(p['command'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps(dict(pid=child.pid,command=p['command'],log=p['log'])))
''' % json.dumps(dict(command=command, log=root+'/logs/'+name+'.log'))
    value = json.loads(transport.ssh([PYTHON, '-c', script], privileged=True))
    value['host_started_utc'] = datetime.now(timezone.utc).isoformat()
    write_evidence(ROOT/'board/measurements'/(name+'_start.json'), value)
    print('STARTED', name, value['pid'], flush=True)
    return value


def completed(transport, name, timeout):
    start = time.monotonic()
    root = REMOTE+'/release/v2'
    while time.monotonic()-start < timeout:
        script = '''import pathlib,json
root=pathlib.Path(%r)
print(json.dumps(dict(running=pathlib.Path('/run/zss_release_v2.json').exists(),log=(root/'logs'/%r).read_text())))
''' % (root, name+'.log')
        value = json.loads(transport.ssh(['python3', '-c', script]))
        match = re.search(r'log .*?/([0-9]{8}T[0-9]{6}Z_[a-f0-9]{8})\.log', value['log'])
        if match and not value['running']:
            return match.group(1)
        time.sleep(3)
    raise TimeoutError('Formal monitor did not stop within its bounded interval')


class Probe:
    def __init__(self, address, output):
        self.address, self.output = address, output
        self.client = None
        self.decoder = None
        self.seq = 0
        self.messages = []
        self.wire = open(output/'wire.jsonl', 'x', encoding='utf-8')
        self.spectra = []
        self.reconnects = []
        self.sent = []

    def connect(self):
        self.client = socket.create_connection((self.address, 9000), timeout=2)
        self.decoder = Decoder()
        self.client.settimeout(.5)
        self.seq = 0

    def disconnect(self):
        if self.client:
            self.client.close()
            self.client = None

    def send(self, name, args=None):
        self.seq += 1
        header = dict(type='command', seq=self.seq, len=0, t_mono=time.monotonic(),
                      command=name, args=args or {})
        self.client.sendall(encode(header))
        self.sent.append(dict(seq=self.seq, command=name, args=args or {},
                              host_mono=time.monotonic()))

    def read_for(self, seconds):
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline:
            try:
                data = self.client.recv(65536)
            except socket.timeout:
                continue
            if not data:
                raise ConnectionError('Unexpected hostlink disconnect')
            for header, payload in self.decoder.feed(data):
                record = dict(header=header, host_received_mono=time.monotonic(),
                              host_received_utc=datetime.now(timezone.utc).isoformat())
                if payload:
                    import hashlib
                    record['payload_sha256'] = hashlib.sha256(payload).hexdigest()
                    if header['type'] == 'spectrum':
                        record['spectrum_index'] = len(self.spectra)
                        self.spectra.append(payload)
                self.messages.append(record)
                self.wire.write(json.dumps(record, allow_nan=False)+'\n')
        self.wire.flush()

    def close(self):
        self.disconnect()
        self.wire.close()
        import numpy as np
        values = np.stack([np.frombuffer(b, dtype='<i2') for b in self.spectra]) if self.spectra else np.empty((0,1024), dtype='<i2')
        np.savez_compressed(str(self.output/'spectra.npz'), power_cdb=values)
        import hashlib
        hashes = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.output.iterdir() if p.is_file()}
        write_evidence(self.output/'manifest.json', dict(files_sha256=hashes))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--name', default='g3_board_r1')
    p.add_argument('--sudo-stdin', action='store_true', required=True)
    args = p.parse_args()
    if not re.fullmatch(r'g3_board_r[1-3]', args.name):
        p.error('Use bounded G3 attempt name')
    transport = Transport(password=sys.stdin.readline().rstrip('\r\n'))
    output = ROOT/'board/measurements'/args.name
    output.mkdir(exist_ok=False)
    error = None
    probe = None
    result = dict(status='STARTED', configuration='A unchanged', RF_TX_requested=False,
                  reconfiguration_requested=False, historical_failures_preserved=True)
    try:
        base = args.name+'_baseline'
        launch(transport, base, 30, False)
        tag = completed(transport, base, 120)
        fetch(tag, 'monitor', output/'baseline_raw')
        print('BASELINE_COMPLETE', tag, flush=True)
        launch(transport, args.name, 420, True)
        address = transport.target.rsplit('@', 1)[-1]
        probe = Probe(address, output)
        deadline = time.monotonic()+90
        while True:
            try:
                probe.connect()
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(2)
        probe.read_for(4)
        for name, command_args in [('ping', {}), ('get_status', {}), ('set_page', {'page':'TGT'}),
                                   ('snapshot', {}), ('tx', {}), ('set_attenuation', {'db':0}),
                                   ('shell', {'cmd':'true'}), ('set_lo', {'hz':1})]:
            probe.send(name, command_args)
        probe.read_for(16)
        from urllib.request import urlopen
        with urlopen('http://'+address+':8080/', timeout=5) as response:
            result['web_page_ok'] = b'Spectrum Sentinel' in response.read()
        with urlopen('http://'+address+':8080/events', timeout=5) as response:
            result['sse_first_line'] = response.readline().decode().strip()
            response.readline()
            result['sse_message'] = response.readline().decode().strip()[:500]
        for index in range(10):
            probe.disconnect()
            begin = time.monotonic()
            # Background worker only; foreground remains free for project work.
            while time.monotonic()-begin < 30:
                time.sleep(min(1, 30-(time.monotonic()-begin)))
            probe.connect()
            probe.read_for(2)
            probe.reconnects.append(dict(index=index+1, disconnected_s=time.monotonic()-begin-2))
            print('RECONNECT', index+1, '/10 PASS', flush=True)
        probe.send('set_page', {'page':'SIG'})
        probe.read_for(3)
        result.update(reconnects=probe.reconnects, sent=probe.sent,
                      received_messages=len(probe.messages), received_spectra=len(probe.spectra),
                      responses=[m for m in probe.messages if m['header']['type'] in ('reply','error')])
        probe.close()
        probe = None
        tag = completed(transport, args.name, 180)
        fetch(tag, 'monitor', output/'enabled_raw')
        result.update(status='MEASURED_REQUIRES_EVALUATION', enabled_tag=tag,
                      calibrated_pl_to_pc_latency='NOT_CERTIFIED_NO_EXACT_FRAME_MAPPING')
    except BaseException as caught:
        error = caught
        result.update(status='FAIL', error=repr(caught))
        try:
            result['emergency_stop'] = transport.ssh(['sh', REMOTE+'/release/v2/scripts/sentinel.sh','stop'], privileged=True)
        except BaseException as stop_error:
            result['stop_error'] = repr(stop_error)
    finally:
        if probe is not None:
            probe.close()
        write_evidence(output/'validation.json', result)
    if error:
        raise error
    print('G3_BOARD_MEASUREMENT_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
