"""Receive-only check of deployed G4d fields; does not start raw DMA or audio."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'src/ps')]
from g3_validate import launch, completed, Probe
from fetch_release_evidence import fetch
from run_x1_board import write_evidence, sha
from x2_transport import Transport, REMOTE, PYTHON


def main():
    if sys.argv[1:] != ['--sudo-stdin']:
        raise ValueError('Require --sudo-stdin; never place credentials in arguments')
    transport = Transport(password=sys.stdin.readline().rstrip('\r\n'))
    name = 'g4d_fields_board_r1'
    output = ROOT/'board/measurements'/name
    output.mkdir(exist_ok=False)
    result = dict(configuration='A', tx_requested=False, raw_dma_requested=False,
                  audio_requested=False, host_started_utc=datetime.now(timezone.utc).isoformat())
    root = REMOTE+'/release/v2'
    probe = None
    try:
        launch(transport, name, 120, True)
        address = transport.target.rsplit('@', 1)[-1]
        deadline = time.monotonic()+90
        while True:
            try:
                with socket.create_connection((address, 9000), timeout=2):
                    break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(1)
        probe = Probe(address, output)
        probe.connect()
        probe.read_for(45)
        headers = [item['header'] for item in probe.messages]
        amc = [h for h in headers if h['type']=='amc']
        telemetry = [h for h in headers if h['type']=='telemetry']
        labels = {'BPSK','PSK-high','QAM','2FSK','GFSK','OOK','AM','FM'}
        def top5_ok(h):
            pairs = h.get('top5', [])
            return (h.get('top5_scope')=='coarse8_softmax' and len(pairs)==5
                and len({p['label'] for p in pairs})==5
                and all(p['label'] in labels and 0<=p['score']<=1 for p in pairs)
                and all(a['score']>=b['score'] for a,b in zip(pairs,pairs[1:]))
                and sum(p['score'] for p in pairs)<=1.00001)
        cpu = [h for h in telemetry if h.get('ps_cpu_pct') is not None]
        checks = dict(real_top5=bool(amc) and all(top5_ok(h) for h in amc),
            real_cpu=bool(cpu) and all(0<=h['ps_cpu_pct']<=100 and
                h.get('ps_cpu_scope')=='all_cores_busy_percent_proc_stat' for h in cpu),
            real_memory=bool(telemetry) and all(
                0<h.get('ps_memory_bytes',0)<=h.get('ps_memory_total_bytes',0) and
                h.get('ps_memory_scope')=='MemTotal_minus_MemAvailable' for h in telemetry))
        result.update(counts=dict(Counter(h['type'] for h in headers)),checks=checks,
            status='PASS' if all(checks.values()) else 'FAIL',
            top5_scope='Eight coarse model classes; uncalibrated; not ten-class posterior',
            first_amc=amc[0] if amc else None,
            last_telemetry=telemetry[-1] if telemetry else None)
    except BaseException as error:
        result.update(status='FAIL', error=repr(error))
        raise
    finally:
        if probe is not None:
            probe.close()
        try:
            result['stop'] = transport.ssh(['sh',root+'/scripts/sentinel.sh','stop'],privileged=True)
            result['postflight'] = json.loads(transport.ssh([PYTHON,'-I',root+'/scripts/y3_postflight.py',
                '--bit',root+'/overlay/sentinel_v2_100m/sentinel_v2_100m.bit'],privileged=True))
            tag = completed(transport,name,60)
            result['tag'] = tag
            fetch(tag,'monitor',output/'board_raw')
        except BaseException as error:
            result.update(status='FAIL',cleanup_error=repr(error))
        result['files_sha256'] = {str(f.relative_to(output)):sha(f)
            for f in output.rglob('*') if f.is_file()}
        write_evidence(output/'validation.json',result)
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':
    main()
