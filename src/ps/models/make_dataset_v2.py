"""4096-point dataset: disk-backed splits, v1 sample IDs and split membership.

The v1 data and generator remain untouched. No test samples enter training.
Production uses 2000 captures per class/SNR; small data are marked SMOKE_ONLY.
"""
import argparse
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import time

import numpy as np

from sim.golden.siggen import gen_mod, to_int16_iq
from src.ps.sentinel.amc.contract import AMC_FS, CAPTURE_LEN_AMC, CLASSES, SCHEMA
from src.ps.sentinel.amc.features import frontend

SEED = 20261102
SNRS = tuple(range(-4, 21, 2))


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def group(task):
    label, snr_index, count = task
    iq = np.empty((count, 2, CAPTURE_LEN_AMC), dtype=np.int16)
    ids = np.empty(count, dtype=np.uint32)
    clipped = 0
    for i in range(count):
        seed = SEED + label*100000000 + snr_index*100000 + i
        rng = np.random.default_rng(seed)
        sps = int(rng.integers(4, 17))
        paths = None
        if rng.random() < .5:
            a, b = (rng.normal(size=2)+1j*rng.normal(size=2))/np.sqrt(2)
            paths = [(0, a), (int(rng.integers(1, sps+1)), .5*b)]
        x = gen_mod(CLASSES[label], CAPTURE_LEN_AMC, sps, fs=AMC_FS,
                    snr_db=SNRS[snr_index], cfo_hz=rng.uniform(-.02, .02)*AMC_FS/sps,
                    phase=rng.uniform(0, 2*np.pi), iq_imb_db=rng.uniform(-1, 1),
                    iq_imb_deg=rng.uniform(-5, 5), multipath=paths, seed=seed)
        x /= np.sqrt(np.mean(np.abs(x)**2))
        words = to_int16_iq(x).reshape(-1, 2)
        clipped += int(np.any((words == -32768) | (words == 32752)))
        iq[i], ids[i] = words.T, seed
    front, features = frontend(iq)
    return label, snr_index, iq, front, features, ids, clipped


def make_dataset(out, per_cell=2000, workers=4):
    if per_cell < 10 or per_cell > 10000 or per_cell % 10:
        raise ValueError('per-cell must be a multiple of ten in [10,10000]')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    counts = dict(train=per_cell*8//10, val=per_cell//10, test=per_cell//10)
    arrays = {}
    for split, count in counts.items():
        directory = out/split
        directory.mkdir()
        arrays[split] = {}
        for key, shape, dtype in (
                ('iq', (2, 4096), np.int16), ('front', (4, 512), np.float32),
                ('features', (24,), np.float32), ('label', (), np.int64),
                ('snr', (), np.int8), ('sample_id', (), np.uint32)):
            arrays[split][key] = np.lib.format.open_memmap(
                directory/(key+'.npy'), mode='w+', dtype=dtype, shape=(130*count,)+shape)
    start, clipping = time.monotonic(), 0
    tasks = [(c, s, per_cell) for c in range(10) for s in range(13)]
    with mp.get_context('spawn').Pool(workers) as pool:
        for done, result in enumerate(pool.imap_unordered(group, tasks), 1):
            c, s, iq, front, features, ids, clips = result
            clipping += clips
            order = np.random.default_rng(SEED+c*13+s).permutation(per_cell)
            position = 0
            for split, count in counts.items():
                selected = order[position:position+count]
                position += count
                section = slice((c*13+s)*count, (c*13+s+1)*count)
                for key, value in dict(iq=iq, front=front, features=features,
                                       sample_id=ids, label=np.full(per_cell, c),
                                       snr=np.full(per_cell, SNRS[s])).items():
                    arrays[split][key][section] = value[selected]
            print(json.dumps(dict(groups=done, total=130, elapsed_s=time.monotonic()-start)), flush=True)
    for values in arrays.values():
        for value in values.values():
            value.flush()
    manifest = dict(schema=SCHEMA, fs=AMC_FS, capture_len=4096, per_cell=per_cell,
                    classes=CLASSES, snrs=SNRS, seed=SEED, smoke_only=per_cell != 2000,
                    clipped_segments=clipping, counts={k:v*130 for k,v in counts.items()},
                    split_rule='v1 per-cell permutation; seed=20261102+class*13+snr_index; 80/10/10',
                    snr_definition='gen_mod occupied-bandwidth SNR; full-band noise scaled fs/bw',
                    frontend='floating PS moments + block8 CNN channels; same code in deployment',
                    files={}, sources={})
    for path in sorted(out.glob('*/*.npy')):
        manifest['files'][path.relative_to(out).as_posix()] = sha(path)
    root = Path(__file__).resolve().parents[3]
    for rel in ('src/ps/models/make_dataset_v2.py', 'sim/golden/siggen.py',
                'src/ps/sentinel/amc/contract.py', 'src/ps/sentinel/amc/features.py'):
        manifest['sources'][rel] = sha(root/rel)
    path = out/'manifest.json'
    path.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    Path(str(path)+'.sha256').write_text(sha(path)+'  manifest.json\n', encoding='ascii')
    print('DATASET_COMPLETE '+json.dumps(manifest['counts']), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', default='data/synthetic/amc_v2')
    p.add_argument('--per-cell', type=int, default=2000)
    p.add_argument('--workers', type=int, default=4)
    args = p.parse_args()
    os.environ['OPENBLAS_NUM_THREADS'] = '1'
    os.environ['OMP_NUM_THREADS'] = '1'
    make_dataset(args.out, args.per_cell, args.workers)
