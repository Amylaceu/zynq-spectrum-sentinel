"""Unprivileged offline inference benchmark. Does not load FPGA or access RF."""
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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True)
    args = p.parse_args()
    root = Path(args.root).resolve()
    manifest = json.loads((root/'manifest.json').read_text())
    for rel, digest in manifest['files'].items():
        path = (root/rel).resolve()
        if root not in path.parents or sha(path) != digest:
            raise ValueError('Benchmark bundle digest/path mismatch')
    sys.path.insert(0, str(root/'ps'))
    from sentinel.amc.infer_np import Predictor
    from sentinel.amc.fine import refine
    model = Predictor(root/'model.npz', 'int8')
    with np.load(root/'captures.npz', allow_pickle=False) as archive:
        iq, labels, ids = archive['iq'], archive['label'], archive['sample_id']
    if len(iq) != 50 or len(set(ids.tolist())) != 50:
        raise ValueError('Need 50 distinct captures')
    for index in range(3):
        model.predict(iq[index])
    rows = []
    for index, capture in enumerate(iq):
        begin = time.perf_counter()
        result = model.predict(capture, fs=480000)[0]
        elapsed = time.perf_counter()-begin
        rows.append(dict(sample_id=int(ids[index]), label=int(labels[index]),
                         predicted=result['label'], coarse=result['coarse'], elapsed_ms=elapsed*1000))
    # Explicitly exercise both refinement paths even if coarse model accuracy
    # is low. These are separately timed, not substituted for end-to-end time.
    fine_times = {}
    for family, label in (('PSK-high', 1), ('QAM', 3)):
        capture = iq[np.flatnonzero(labels == label)[0]]
        begin = time.perf_counter()
        refine(capture, family)
        fine_times[family] = (time.perf_counter()-begin)*1000
    values = np.asarray([row['elapsed_ms'] for row in rows])
    result = dict(step='X4', mode='offline_synthetic_on_board_no_rf',
                  system=platform.platform(), python=sys.version, numpy=np.__version__,
                  boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                  capture_len=4096, fs=480000, precision='mixed INT8 MAC/FP32 scale',
                  smoke_only=model.metadata['smoke_only'], bundle_sha256=sha(root/'manifest.json'),
                  rows=rows, median_ms=float(np.median(values)), p95_ms=float(np.quantile(values, .95)),
                  max_ms=float(values.max()), all_under_100ms=bool(np.all(values <= 100)),
                  standalone_refine_ms=fine_times)
    out = root/'result.json'
    with out.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    Path(str(out)+'.sha256').write_text(sha(out)+'  result.json\n', encoding='ascii')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
