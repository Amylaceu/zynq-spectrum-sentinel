"""Freeze finite-frame Welch/capture/CFAR vectors without touching old evidence."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim.golden.cfar_x1 import detect_x1


def main():
    destination = ROOT / 'data/reference/cfar/x1_diagnostic_r1'
    destination.mkdir(parents=True, exist_ok=False)
    rng = np.random.default_rng(74123)
    old = np.zeros(2048, dtype=np.int64)
    inputs, outputs, stats = [], [], []
    for frame in range(8):
        raw = rng.integers(1, 50, 2048, dtype=np.int64)
        raw[150+frame*100:154+frame*100] = 1000000
        raw[2040:2046] = 10000 * (frame + 1)
        if frame == 7:
            raw[:] = 0
        old = old + ((raw - old) >> 3)
        inputs.extend(raw.tolist())
        outputs.extend(old.tolist())
        _, _, cluster = detect_x1(old)
        stats.extend([len(cluster.targets), cluster.hit_count, cluster.raw_count,
                      cluster.filtered_count, cluster.candidate_count, cluster.status_latch])
    for name, values in [('diag_input.hex', inputs), ('diag_power.hex', outputs), ('diag_stats.hex', stats)]:
        (destination/name).write_text(''.join('%08x\n' % value for value in values), encoding='ascii')
    record = {'frames': 8, 'bins': 2048, 'average_shift': 3,
        'files_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.iterdir()}}
    path = destination/'manifest.json'
    path.write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    Path(str(path)+'.sha256').write_text(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name+'\n')


if __name__ == '__main__':
    main()
