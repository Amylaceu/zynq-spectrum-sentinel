"""Benchmark synthetic contiguous IQ on the board; no sudo, RF, PL or audio I/O."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from x2_transport import ROOT, REMOTE, PYTHON, Transport, sha, write_evidence


SCRIPT = '''import hashlib,json,pathlib,sys,time
import numpy as np
p=json.load(sys.stdin);source=pathlib.Path(p['source'])
if hashlib.sha256(source.read_bytes()).hexdigest()!=p['sha256']:raise ValueError('Source digest')
import importlib.util
spec=importlib.util.spec_from_file_location('fm_stream_y3_benchmark',str(source))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
block_ms=int(p['block_ms']);n=block_ms*480;repetitions=10000//block_ms
t=np.arange(n)/480000
iq=np.exp(2j*np.pi*np.cumsum(10000*np.sin(2*np.pi*1000*t))/480000).astype(np.complex64)
warm=module.FmStream();warm.process(iq,0)
fm=module.FmStream();elapsed=[];samples=0
started=time.perf_counter()
for index in range(repetitions):
 tick=time.perf_counter();audio=fm.process(iq,index*n);words=module.pcm24_words(audio)
 elapsed.append(time.perf_counter()-tick);samples+=len(words)
wall=time.perf_counter()-started
realtime_factor=10/wall;deadline_s=block_ms/1000
value=dict(schema='y3-ps-synthetic-throughput-v2',
 status='PASS' if realtime_factor>=1.5 and max(elapsed)<deadline_s else 'FAIL',
 scope='Synthetic480k contiguous IQ CPU+PCM benchmark only; no RF/DMA/I2S/playback guarantee',
 numpy=np.__version__,python=sys.version,processed_input_seconds=10,elapsed_s=wall,
 block_ms=block_ms,block_deadline_s=deadline_s,blocks=repetitions,
 realtime_factor=realtime_factor,max_block_seconds=max(elapsed),
 p95_block_seconds=float(np.percentile(elapsed,95)),median_block_seconds=float(np.median(elapsed)),
 all_blocks_under_deadline=bool(max(elapsed)<deadline_s),
 input_samples=fm.input_samples,output_samples=samples,expected_output_samples=480000,
 clipped_samples=fm.clipped_samples,source_sha256=p['sha256'],RF_TX_requested=False)
if samples!=480000:raise ValueError('Audio sample accounting mismatch')
print(json.dumps(value))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--block-ms', type=int, choices=(20, 40, 100), default=100)
    args = parser.parse_args()
    suffix = ('_r%d' if args.block_ms == 100 else '_%dms_r%d')
    tag = suffix % ((args.attempt,) if args.block_ms == 100 else (args.block_ms, args.attempt))
    output = ROOT/('board/measurements/y3_fallback_cpu%s.json' % tag)
    log = ROOT/('logs/Y3_fallback_cpu%s.log' % tag)
    if output.exists() or log.exists():
        raise FileExistsError('Preserve earlier benchmark')
    source = ROOT/'src/ps/sentinel/fm_stream_y3.py'
    target = REMOTE+'/setup/y3_cpu%s/fm_stream_y3.py' % tag
    transport = Transport()
    transport.ssh(['mkdir', target.rsplit('/', 1)[0]])
    transport.copy(source, transport.target+':'+target)
    text = transport.ssh([PYTHON, '-I', '-c', SCRIPT],
        payload=json.dumps(dict(source=target, sha256=sha(source),
                                block_ms=args.block_ms)), timeout=180)
    value = json.loads(text)
    log.write_text(text, encoding='utf-8')
    value.update(recorded_at_pc=datetime.now(timezone.utc).isoformat(),
                 runner_sha256=sha(Path(__file__)), log_sha256=sha(log))
    write_evidence(output, value)
    print(json.dumps(value, indent=2))


if __name__ == '__main__':
    main()
