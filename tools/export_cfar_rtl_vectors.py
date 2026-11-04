"""N3 independent golden vectors: wrap boundaries, fixed-point endpoints, lists."""
import hashlib
import json
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim.golden.cfar import cfar, cluster, alpha_for_pfa, pack_targets
from sim.golden.spectrum import to_db_q88


def main():
    out = ROOT / 'data/reference/cfar/n3'
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0x20261103)
    cases = []
    for mode in ('CA', 'GO', 'SO'):
        for boundary in ('interior', 'wrap'):
            p = rng.integers(700, 1300, 2048, dtype=np.uint32)
            positions = [(180, 184), (650, 654), (1500, 1502)]
            if boundary == 'wrap': positions += [(0, 3), (2045, 2047)]
            for a, b in positions: p[a:b+1] = 1000000
            p[1021:1028] = 2000000
            cases.append(dict(name=f'{mode}_{boundary}', mode=mode, n=16, g=2,
                              alpha=alpha_for_pfa(1e-3, 16, mode), dc=3, gap=2, p=p))
    base = dict(mode='CA', n=4, g=1, alpha=256, dc=-1, gap=2)
    def add(name, p, **cfg): cases.append(dict(base, name=name, p=p, **cfg))
    add('threshold_saturation', np.full(2048, 0xffffffff, dtype=np.uint32), alpha=65535)
    p = np.zeros(2048, dtype=np.uint32); p[::8] = 0xffffffff
    p[1:4] = 0xffffffff
    add('list_overflow_and_sum_saturation', p, alpha=0, gap=0)
    add('zero_and_empty', np.zeros(2048, dtype=np.uint32))
    add('strict_equal', np.full(2048, 100, dtype=np.uint32))
    add('minimum_window', rng.integers(0, 2**32, 2048, dtype=np.uint32), n=1, g=0, alpha=511, gap=0)
    add('maximum_window', rng.integers(0, 2**32, 2048, dtype=np.uint32), mode='GO', n=64, g=31, alpha=256, gap=5)
    # An adaptive threshold can leave a higher-power non-hit inside a bridged gap.
    p = np.full(2048, 10, dtype=np.uint32)
    p[50:55] = [500, 800, 900, 700, 500];p[54:60] = 10000
    add('cluster_gap_peak', p, mode='SO', n=2, g=0, alpha=512, gap=3)
    contents = {key: [] for key in ('input', 'threshold', 'db', 'hit', 'targets', 'count', 'config', 'occupancy')}
    occupancy = np.zeros(2048, dtype=np.uint16)
    metadata = []
    for case in cases:
        p = case.pop('p')
        threshold, hit = cfar(p, case['mode'], case['n'], case['g'], case['alpha'], case['dc'])
        targets = cluster(hit, p, case['gap'])
        contents['input'].extend(map(int, p));contents['threshold'].extend(map(int, threshold))
        contents['db'].extend(int(x) & 65535 for x in to_db_q88(threshold))
        contents['hit'].extend(map(int, hit))
        records = [int.from_bytes(pack_targets(targets[i:i+1]), 'little') for i in range(len(targets))]
        contents['targets'].extend(records + [0]*(32-len(records)))
        contents['count'].append(len(records))
        contents['config'].extend([1+2*('CA','GO','SO').index(case['mode']), case['n'].bit_length()-1,
                                  case['g'], case['alpha'], case['dc'] & 255, case['gap']])
        occupancy = np.minimum(occupancy.astype(np.uint32) + hit, 65535).astype(np.uint16)
        contents['occupancy'].extend(map(int, occupancy))
        metadata.append(dict(case, targets=len(records), hits=int(hit.sum())))
    contents['targets_words'] = [(word >> (32*lane)) & 0xffffffff for word in contents['targets'] for lane in range(4)]
    sha = {}
    for name, values in contents.items():
        width = 32 if name == 'targets' else 8
        raw = ''.join(f'{x:0{width}x}\n' for x in values).encode()
        path = out / (name + '.hex');path.write_bytes(raw);sha[path.name]=hashlib.sha256(raw).hexdigest()
    (out / 'manifest.json').write_bytes((json.dumps(dict(cases=metadata, sha256=sha),indent=2)+'\n').encode())
    print('N3_VECTORS_PASS', len(cases), len(contents['input']))


if __name__ == '__main__': main()
