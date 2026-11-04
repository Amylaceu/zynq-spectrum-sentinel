"""Create X1-only cluster vectors; do not touch accepted N3/N4 vectors."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim.golden.cfar import pack_targets
from sim.golden.cfar_x1 import cluster_x1, mask_bins


def make_cases():
    rng = np.random.default_rng(20261103)
    cases = []

    def add(name, power, hit=None, width=2, gap=6, masks=(), dc=-1):
        cases.append(dict(name=name, power=power, hit=(power > 0) if hit is None else hit,
                          width=width, gap=gap, masks=masks, dc=dc))

    p = np.zeros(2048, dtype=np.uint32)
    add('empty', p.copy())
    p[180:184] = 300; p[650:655] = 200; p[1500:1503] = 100
    add('three_clusters', p.copy())
    p = np.zeros(2048, dtype=np.uint32); p[::4] = np.arange(1, 513)
    add('top32_strongest_at_right', p.copy(), width=0, gap=0)
    p[::4] = 100
    add('top32_ties_start_ascending', p.copy(), width=1, gap=0)
    p = np.zeros(2048, dtype=np.uint32); p[::8] = 500
    add('all_narrow_removed_no_overflow', p.copy(), width=2, gap=0)
    p[10:12] = 50; p[2045:2048] = 90
    add('width_filter_mixed_and_last_bin', p.copy(), width=2, gap=0)
    p = np.zeros(2048, dtype=np.uint32); p[[2, 9, 17, 2047]] = 10
    h = (p > 0).astype(np.uint8); p[5] = 90
    add('gap_boundary_and_nonhit_peak', p.copy(), h.copy(), width=1)
    p = np.ones(2048, dtype=np.uint32); p[1024] = 0xffffffff
    add('dc_hard_boundary', p.copy(), width=1, gap=255, dc=0)
    masks = [(i * 128, i * 128 + 2) for i in range(16)]
    add('sixteen_masks_split_long_gaps', p.copy(), width=1, gap=255, masks=masks)
    add('overlapping_masks', p.copy(), masks=[(0, 8), (7, 15), (2040, 2047)])
    add('saturating_sum', np.full(2048, 0xffffffff, dtype=np.uint32))
    p = np.zeros(2048, dtype=np.uint32); p[[0, 2047]] = 100
    add('edges_do_not_wrap', p, width=1, gap=255)
    for i in range(8):
        p = rng.integers(0, 2**32, 2048, dtype=np.uint32)
        h = (rng.random(2048) < .15).astype(np.uint8)
        masks = [(int(s), int(s) + 2) for s in rng.integers(0, 2040, 16)]
        add('random_%d' % i, p, h, width=i % 4, gap=i % 7, masks=masks)
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'data/reference/cfar/x1')
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Preserve vectors: choose a new --out or verify existing manifest')
    cases = make_cases()
    contents = {key: [] for key in ('power', 'hit', 'blocked', 'config', 'targets', 'stats')}
    metadata = []
    for case in cases:
        p, h = case['power'], case['hit']
        blocked = mask_bins(2048, case['masks'], case['dc'])
        result = cluster_x1(h, p, case['width'], case['gap'], case['masks'], case['dc'])
        contents['power'].extend(map(int, p))
        contents['hit'].extend(map(int, h))
        contents['blocked'].extend(map(int, blocked))
        contents['config'].extend([case['gap'], case['width']])
        records = [int.from_bytes(pack_targets(result.targets[i:i+1]), 'little')
                   for i in range(len(result.targets))]
        contents['targets'].extend(records + [0] * (32 - len(records)))
        contents['stats'].extend([len(records), result.raw_count, result.filtered_count,
                                  result.candidate_count, result.hit_count, result.status_latch])
        metadata.append({'name': case['name'], 'width': case['width'], 'gap': case['gap'],
                         'mask_table': case['masks'], 'dc_mask': case['dc'], 'targets': len(records)})
    args.out.mkdir(parents=True)
    hashes = {}
    for name, values in contents.items():
        width = 32 if name == 'targets' else 8
        path = args.out / (name + '.hex')
        path.write_bytes(''.join(('%0*x' % (width, v)) + '\n' for v in values).encode('ascii'))
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = args.out / 'manifest.json'
    manifest.write_text(json.dumps({'scope': 'synthetic X1 clustering only; no hardware acceptance',
                                    'cases': metadata, 'sha256': hashes}, indent=2) + '\n', encoding='utf-8')
    (args.out / 'manifest.json.sha256').write_text(
        hashlib.sha256(manifest.read_bytes()).hexdigest() + '  manifest.json\n', encoding='ascii')
    print('X1_CLUSTER_VECTORS_PASS', len(cases), len(contents['power']))


if __name__ == '__main__':
    main()
