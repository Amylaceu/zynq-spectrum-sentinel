"""Inspect blind refinement using validation data only, never holdout truth.

This diagnostic does not fit thresholds or modify a model. Save individual
validation statistics so the reason for a subsequent round is reviewable.
"""
import argparse
import json
from pathlib import Path
import re
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.ps.sentinel.amc.contract import CLASSES
from src.ps.sentinel.amc.fine import refine
from x2_transport import sha, write_evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--revision', default='', help='Optional immutable diagnostic suffix')
    args = parser.parse_args()
    if args.revision and not re.fullmatch(r'[a-z0-9_]+', args.revision):
        parser.error('revision must contain lowercase letters, digits or underscores')
    data = ROOT/'data/synthetic/amc_v2/val'
    labels = np.load(data/'label.npy')
    snrs = np.load(data/'snr.npy')
    iq = np.load(data/'iq.npy', mmap_mode='r')
    ids = np.load(data/'sample_id.npy')
    rows, summaries = [], {}
    for label in (1, 2, 3, 4):
        indices = np.flatnonzero((labels == label) & (snrs == 10))
        group = []
        for index in indices:
            result = refine(iq[index], 'PSK-high' if label < 3 else 'QAM')
            row = {k: v for k, v in result.items() if k != 'symbols'}
            row.update(truth=CLASSES[label], sample_id=int(ids[index]))
            rows.append(row)
            group.append(row)
        summaries[CLASSES[label]] = dict(
            count=len(group), recall=float(np.mean([r['label'] == CLASSES[label] for r in group])),
            quantiles={key: np.quantile([r[key] for r in group], [.1, .5, .9]).tolist()
                       for key in ('sps', 'rate_prominence', 'c40', 'c42')})
    result = dict(split='validation_only', snr_db=10, rows=rows, summary=summaries,
                  sources_sha256={p.relative_to(ROOT).as_posix(): sha(p) for p in
                      [Path(__file__), ROOT/'src/ps/sentinel/amc/fine.py', data/'iq.npy',
                       data/'label.npy', data/'snr.npy', data/'sample_id.npy']})
    suffix = '_'+args.revision if args.revision else ''
    result.update(attempt=args.attempt, revision=args.revision)
    write_evidence(ROOT/'board/measurements'/('x4_validation_diagnostic_r'+str(args.attempt)+suffix+'.json'), result)
    print(json.dumps(summaries, indent=2), flush=True)


if __name__ == '__main__':
    main()
