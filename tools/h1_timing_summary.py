"""Summarize measured 10-tile timing without inventing C API substage timing."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src/ps'))
from sentinel.panorama import stitch, SAMPLE_RATE_HZ
from sentinel.panorama_capture import write_json, digest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise FileExistsError('Preserve earlier timing evidence')
    if digest(args.input) != Path(str(args.input)+'.sha256').read_text().split()[0]:
        raise ValueError('Input digest differs')
    data = json.loads(args.input.read_text())
    if data['status'] != 'PASS_SNAPSHOT_SCAN' or len(data['tiles']) != 10:
        raise ValueError('Require 10 actually captured timing tiles')
    timings = [tile['timing'] for tile in data['tiles']]
    sums = {key: sum(t[key] for t in timings) for key in timings[0]}
    body = sums.pop('tile_total_before_progress_write_s')
    # Coverage proof uses flat planning PSD, explicitly unrelated to RF evidence.
    baseband = np.fft.fftshift(np.fft.fftfreq(4096, 1/SAMPLE_RATE_HZ))
    centers = list(range(75000000, 507000001, 18000000))
    if centers[-1] != 507000000:
        centers.append(507000000)
    _, _, count = stitch([(lo, baseband, np.ones(len(baseband))) for lo in centers], 'A')
    record = dict(status='MEASURED_PARTIAL_DECOMPOSITION', group='A', tiles=10,
        source_sha256=digest(args.input), source=str(args.input),
        elapsed_including_init_restore_s=data['elapsed_s'], tile_body_s=body,
        measured_stage_totals_s=sums,
        init_restore_progress_and_outer_overhead_s=data['elapsed_s']-body,
        per_tile=timings,
        unavailable_separate_timings=['LO lock only', 'sample-rate change only', 'RF bandwidth only'],
        limitation='Accepted native configure API couples rate/LO/bandwidth on every call. '
                   'No fabricated independent tuning breakdown. Init/restore outer time not isolated.',
        s1_18mhz_planning=dict(scope='NUMERIC_COVERAGE_PLANNING_NOT_BOARD_MEASUREMENT',
            tiles=len(centers), missing_bins=int(np.count_nonzero(count == 0)),
            compatible_with_current_dc_mask=not bool(np.any(count == 0))),
        historical_55_tile_s=78.34977659200013, optimized_scan_accepted=False,
        one_hour_test='DEFERRED_BY_USER')
    write_json(args.output, record)
    print(json.dumps({k: record[k] for k in ('status','elapsed_including_init_restore_s',
        'measured_stage_totals_s','s1_18mhz_planning')}, indent=2))


if __name__ == '__main__':
    main()
