"""Paired offline AMC runtime experiment; no FPGA, RF, sudo or DMA access."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

import numpy as np


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def same(left, right):
    if isinstance(left, dict):
        assert left.keys() == right.keys()
        for key in left:
            same(left[key], right[key])
    elif isinstance(left, list):
        assert len(left) == len(right)
        for a, b in zip(left, right):
            same(a, b)
    else:
        np.testing.assert_array_equal(left, right)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    manifest = json.loads((root/'manifest.json').read_text())
    for rel, digest in manifest['files'].items():
        path = (root/rel).resolve()
        if root not in path.parents or sha(path) != digest:
            raise ValueError('Bundle digest/path mismatch')
    sys.path.insert(0, str(root/'ps'))
    from sentinel.amc.infer_np import Predictor
    from sentinel.amc.infer_cached import CachedPredictor
    engines = (Predictor(root/'model.npz'), CachedPredictor(root/'model.npz'),
               CachedPredictor(root/'model.npz', accumulator='exact-fp32'))
    names = ('reference_int32', 'cached_int32', 'cached_exact_fp32')
    with np.load(root/'captures.npz', allow_pickle=False) as archive:
        iq, labels, ids = archive['iq'], archive['label'], archive['sample_id']
    if iq.shape != (50, 2, 4096) or iq.dtype != np.int16 or len(set(ids.tolist())) != 50:
        raise ValueError('Need 50 distinct 4096-sample holdout captures')
    # np.bincount requires native intp on the 32-bit Cortex-A9 NumPy build;
    # saved PC labels are int64. Values are bounded before narrowing.
    if labels.shape != (50,) or np.any((labels < 0) | (labels >= 10)):
        raise ValueError('Class labels must be in 0..9')
    if not np.array_equal(np.bincount(labels.astype(np.intp), minlength=10), np.full(10, 5)):
        raise ValueError('Need five captures per class')
    for engine in engines:
        for index in range(3):
            engine.predict(iq[index])
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    durations = {name: [] for name in names}
    rows = []
    for repeat in range(3):
        for index, capture in enumerate(iq):
            outputs = {}
            for pos in range(3):
                which = (pos+index+repeat) % 3
                start = time.perf_counter()
                outputs[which] = engines[which].predict(capture)
                elapsed = (time.perf_counter()-start)*1000
                durations[names[which]].append(elapsed)
                rows.append(dict(repeat=repeat, sample_id=int(ids[index]),
                                 label=int(labels[index]), engine=names[which],
                                 elapsed_ms=elapsed, predicted=outputs[which][0]['label'],
                                 confidence=outputs[which][0]['confidence']))
            same(outputs[0], outputs[1])
            same(outputs[0], outputs[2])
    if Path('/proc/sys/kernel/random/boot_id').read_text().strip() != boot:
        raise ValueError('Board rebooted during experiment')
    stats = {name: dict(count=len(values), median_ms=float(np.median(values)),
                        p95_ms=float(np.percentile(values, 95)), max_ms=float(np.max(values)),
                        all_under_100ms=bool(np.all(np.asarray(values) <= 100)))
             for name, values in durations.items()}
    result = dict(status='PASS_EQUIVALENCE_BOARD_OFFLINE', board_tested=True,
                  experiment='Runtime comparison only; not another training/accuracy acceptance round',
                  x4_acceptance_status='FAIL', no_rf_access=True,
                  capture_len=4096, fs_hz=480000, exact_prediction_captures=50,
                  repeats=3, rows=rows, timing=stats, boot_id=boot,
                  model_sha256=sha(root/'model.npz'), bundle_sha256=sha(root/'manifest.json'),
                  extra_cache_bytes=engines[1].cache_bytes,
                  median_speedup={name: stats[names[0]]['median_ms']/stats[name]['median_ms']
                                  for name in names[1:]},
                  system=platform.platform(), python=sys.version, numpy=np.__version__,
                  thread_env={key: os.environ.get(key) for key in
                              ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')},
                  limitations=['Synthetic holdout only; no new RF or end-to-end UI acceptance',
                               'Original accuracy and latency failures remain',
                               'exact-fp32 uses floating-point GEMM, not INT32 accumulation'])
    out = root/'result.json'
    with out.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    Path(str(out)+'.sha256').write_text(sha(out)+'  result.json\n', encoding='ascii')
    print(json.dumps(dict(status=result['status'], timing=stats, speedup=result['median_speedup'])), flush=True)


if __name__ == '__main__':
    main()
