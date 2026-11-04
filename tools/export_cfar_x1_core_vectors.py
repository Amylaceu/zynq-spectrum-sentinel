"""X1 integrated CA/GO/SO, mask, clustering and occupancy reference vectors."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim.golden.cfar import alpha_for_pfa, pack_targets
from sim.golden.cfar_x1 import detect_x1
from sim.golden.spectrum import to_db_q88


def make_cases():
    rng = np.random.default_rng(0x20261103)
    cases = []

    def add(name, power, **kwargs):
        cfg = dict(name=name, power=power, mode='CA', n=16, g=2,
                   alpha=1974, dc=3, gap=6, width=2, masks=[])
        cfg.update(kwargs)
        cases.append(cfg)

    for mode in ('CA', 'GO', 'SO'):
        for edge in (False, True):
            power = rng.integers(700, 1300, 2048, dtype=np.uint32)
            bounds = [(180, 184), (650, 654), (1500, 1502)]
            if edge:
                bounds += [(0, 3), (2045, 2047)]
            for a, b in bounds:
                power[a:b+1] = 1000000
            power[1021:1028] = 2000000
            add(mode + ('_wrap' if edge else '_interior'), power, mode=mode,
                alpha=alpha_for_pfa(1e-3, 16, mode))
    add('zero_empty', np.zeros(2048, dtype=np.uint32))
    add('strict_equal', np.full(2048, 100, dtype=np.uint32), alpha=256, dc=-1)
    add('threshold_saturation', np.full(2048, 0xffffffff, dtype=np.uint32), alpha=65535)
    power = np.zeros(2048, dtype=np.uint32); power[::8] = np.arange(1, 257) * 10000
    add('strongest_on_right', power.copy(), alpha=0, width=1, gap=0, dc=-1)
    add('narrow_filter_before_capacity', power.copy(), alpha=0, width=2, gap=0, dc=-1)
    power = np.full(2048, 100, dtype=np.uint32)
    masks = [(i*128+31, i*128+31) for i in range(16)]
    add('sixteen_hard_boundaries', power.copy(), alpha=0, dc=-1, masks=masks)
    add('overlapping_masks', power.copy(), alpha=0, dc=-1, masks=[(0, 6), (4, 10), (2040, 2047)])
    add('dc_hard_boundary', power.copy(), alpha=0, dc=0, gap=255)
    power = np.full(2048, 10, dtype=np.uint32)
    power[50:55] = [500, 800, 900, 700, 500]; power[54:60] = 10000
    add('gap_nonhit_peak', power, mode='SO', n=2, g=0, alpha=512, dc=-1, gap=3, width=1)
    for index, mode in enumerate(('CA', 'GO', 'SO')):
        power = rng.integers(0, 2**32, 2048, dtype=np.uint32)
        add('random_'+mode, power, mode=mode, n=(1, 16, 64)[index],
            g=(0, 2, 31)[index], alpha=256, dc=-1, gap=index, width=index,
            masks=[(80, 85), (700, 706), (1400, 1410)])
    assert len(cases) == 18
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Preserve prior vectors; use a new output directory')
    contents = {k: [] for k in ('input', 'threshold', 'db', 'hit', 'targets', 'targets_words',
                               'count', 'config', 'occupancy', 'stats')}
    metadata = []
    occupancy = np.zeros(2048, dtype=np.uint16)
    for case in make_cases():
        power = case.pop('power')
        threshold, hit, result = detect_x1(power, mode=case['mode'], n=case['n'], g=case['g'],
            alpha_q88=case['alpha'], dc_mask=case['dc'], min_width_bins=case['width'],
            merge_gap_bins=case['gap'], mask_table=case['masks'])
        contents['input'].extend(map(int, power))
        contents['threshold'].extend(map(int, threshold))
        contents['hit'].extend(map(int, hit))
        contents['db'].extend(int(x) & 65535 for x in to_db_q88(threshold))
        records = [int.from_bytes(pack_targets(result.targets[i:i+1]), 'little') for i in range(len(result.targets))]
        contents['targets'].extend(records + [0] * (32 - len(records)))
        contents['count'].append(len(records))
        masks = [a | (b << 16) for a, b in case['masks']]
        contents['config'].extend([1+2*('CA', 'GO', 'SO').index(case['mode']), case['n'].bit_length()-1,
            case['g'], case['alpha'], case['dc'] & 255, case['gap'], case['width'], len(masks)] + masks + [0]*(16-len(masks)))
        occupancy = np.minimum(occupancy.astype(np.uint32) + hit, 65535).astype(np.uint16)
        contents['occupancy'].extend(map(int, occupancy))
        contents['stats'].extend([len(records), result.raw_count, result.filtered_count,
            result.candidate_count, result.hit_count, result.status_latch, int(result.hit_count>0)])
        metadata.append(dict(case, targets=len(records), hits=result.hit_count))
    contents['targets_words'] = [(word >> (32*lane)) & 0xffffffff for word in contents['targets'] for lane in range(4)]
    args.out.mkdir(parents=True)
    hashes = {}
    for name, values in contents.items():
        width = 32 if name == 'targets' else 8
        path = args.out / (name+'.hex')
        path.write_bytes(''.join(('%0*x' % (width, v))+'\n' for v in values).encode('ascii'))
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    path = args.out / 'manifest.json'
    path.write_text(json.dumps({'scope':'Synthetic integrated X1 CFAR vectors; no board/RF claims',
        'cases':metadata, 'sha256':hashes}, indent=2)+'\n', encoding='utf-8')
    path.with_name(path.name+'.sha256').write_text(hashlib.sha256(path.read_bytes()).hexdigest()+'  manifest.json\n', encoding='ascii')
    print('X1_CORE_VECTORS_PASS', len(metadata), len(contents['input']))


if __name__ == '__main__':
    main()
