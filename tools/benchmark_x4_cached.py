"""No-training PC equivalence/latency experiment; no board or RF access."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
from time import perf_counter_ns

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.ps.sentinel.amc.features import frontend
from src.ps.sentinel.amc.infer_np import Predictor
from src.ps.sentinel.amc.infer_cached import CachedPredictor


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    Path(str(path)+'.sha256').write_text(sha(path)+'  '+path.name+'\n', encoding='ascii')


def same_prediction(left, right):
    if isinstance(left, dict):
        assert left.keys() == right.keys()
        for key in left:
            same_prediction(left[key], right[key])
    elif isinstance(left, list):
        assert len(left) == len(right)
        for a,b in zip(left,right):
            same_prediction(a,b)
    else:
        np.testing.assert_array_equal(left,right)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--attempt',type=int,choices=(1,2,3),required=True)
    args=p.parse_args()
    output=ROOT/'sim/results'/('x4_cached_pc_r%d.json'%args.attempt)
    if output.exists():
        raise FileExistsError(output)
    model=ROOT/'src/ps/models/weights/amc_v2/round_3/model.npz'
    expected='5e752f90523ea92d95bbd0ac3fe40ff70c12d9f0023373c36c22acd495508935'
    if sha(model)!=expected:
        raise ValueError('Selected frozen X4 model changed')
    data=ROOT/'data/synthetic/amc_v2/test'
    iq=np.load(data/'iq.npy',mmap_mode='r')
    labels=np.load(data/'label.npy',mmap_mode='r')
    snrs=np.load(data/'snr.npy',mmap_mode='r')
    indices=np.flatnonzero(snrs==10)
    counts=np.bincount(labels[indices],minlength=10)
    if not np.array_equal(counts,np.full(10,200)):
        raise ValueError('Need complete balanced 2000-capture SNR10 test subset')
    names=('reference_int32','cached_int32','cached_exact_fp32')
    engines=(Predictor(model),CachedPredictor(model),
             CachedPredictor(model,accumulator='exact-fp32'))
    for offset in range(0,len(indices),16):
        front,features=frontend(iq[indices[offset:offset+16]])
        expected_logits=engines[0].logits(front,features)
        for engine in engines[1:]:
            np.testing.assert_array_equal(engine.logits(front,features),expected_logits)
    # Complete prediction includes the slower blind synchronization/refinement.
    selected=np.concatenate([np.flatnonzero((labels==k)&(snrs==10))[:5] for k in range(10)])
    durations={name:[] for name in names}
    predictions=[]
    for engine in engines:
        engine.predict(iq[selected[0]])  # equal unmeasured warmup
    for repeat in range(3):
        for sample,index in enumerate(selected):
            outputs={}
            # Rotate order to reduce thermal/scheduler bias; full per-sample
            # paired data is retained, not just fastest or median timings.
            for pos in range(3):
                which=(pos+sample+repeat)%3
                start=perf_counter_ns()
                outputs[which]=engines[which].predict(iq[index])
                durations[names[which]].append((perf_counter_ns()-start)/1e6)
            for which in (1,2):
                same_prediction(outputs[0],outputs[which])
            if repeat==0:
                predictions.append(outputs[0][0]['class_index'])
    raw=output.with_suffix('.npz')
    with raw.open('xb') as stream:
        np.savez_compressed(stream,logit_indices=indices,prediction_indices=selected,
                            prediction_class=predictions,**durations)
    Path(str(raw)+'.sha256').write_text(sha(raw)+'  '+raw.name+'\n',encoding='ascii')
    files=[Path(__file__), ROOT/'src/ps/sentinel/amc/infer_cached.py']
    files+=sorted((ROOT/'src/ps/sentinel/amc').glob('*.py'))
    for path in set(files):
        ast.parse(path.read_text(encoding='utf-8'),feature_version=(3,8))
    stats={name:dict(count=len(value),median_ms=float(np.median(value)),
                     p95_ms=float(np.percentile(value,95)),max_ms=float(np.max(value)))
           for name,value in durations.items()}
    value=dict(status='PASS_EQUIVALENCE_PC_ONLY',recorded_at=datetime.now(timezone.utc).isoformat(),
               experiment='Opt-in arithmetic/cache optimization, not training or another X4 acceptance round',
               board_tested=False,x4_acceptance_status='FAIL',
               limitations=['PC timings are not Cortex-A9 timings',
                            'The original three accuracy and latency failures remain',
                            'No deployment runtime or model selection changed'],
               model_sha256=sha(model),logit_exact_captures=len(indices),
               complete_prediction_exact_captures=len(selected),timing=stats,
               extra_cache_bytes=engines[1].cache_bytes,
               median_speedup={name:stats[names[0]]['median_ms']/stats[name]['median_ms'] for name in names[1:]},
               runtime=dict(python=sys.version,numpy=np.__version__,platform=platform.platform(),
                            thread_env={key:os.environ.get(key) for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')}),
               source_sha256={path.relative_to(ROOT).as_posix():sha(path) for path in set(files)},
               subset_metadata_sha256={path.relative_to(ROOT).as_posix():sha(path) for path in (data/'label.npy',data/'snr.npy',data/'sample_id.npy')},
               raw_sha256=sha(raw))
    write_json(output,value)
    print(json.dumps(value,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
