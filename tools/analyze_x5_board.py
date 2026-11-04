"""Independently audit captured X5 packets, votes and quantitative X5/Y2 gates.

No RF operation is performed. New Y2 targets are reported separately and never
replace the original X5 limits. Human visual acceptance remains a separate gate.
"""
import argparse
from collections import Counter, deque
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import numpy as np

from run_x5_board import verify_captures
from x2_transport import ROOT, sha, verified, write_evidence


def checked_number(value):
    if not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError('Missing/nonfinite measured value')
    return float(value)


def decode_processing_status(value):
    """perf_mon: bits 0/1 are faults; bits 2..4 are latency handshake state."""
    if type(value) is not int or value < 0 or value & ~0x1f:
        raise ValueError('Invalid/reserved processing status')
    if value & 3:
        raise ValueError('Processing overflow/error fault')
    return dict(latency_valid=bool(value & 4), marker_pending=bool(value & 8),
                arm_wait=bool(value & 16))


def check_votes(records):
    histories = {}
    first_tracks = set()
    first_seen = {}
    previous_applied = -math.inf
    for record in records:
        key = record['track']
        observed = checked_number(record['first_seen_monotonic_s'])
        applied = checked_number(record['ui_applied_monotonic_s'])
        if observed > applied or applied < previous_applied:
            raise ValueError('Inconsistent observation/UI chronology')
        if observed != first_seen.setdefault(key, observed):
            raise ValueError('Track first-seen timestamp changed')
        previous_applied = applied
        score = checked_number(record['score'])
        if not 0 <= score <= 1:
            raise ValueError('Invalid raw classifier score')
        votes = histories.setdefault(key, deque(maxlen=5))
        votes.append((record['prediction'], score))
        if [list(v) for v in votes] != record['votes']:
            raise ValueError('Per-track vote history mismatch')
        counts = Counter(label for label, _ in votes)
        winners = {label for label, count in counts.items() if count == max(counts.values())}
        label = next(label for label, _ in reversed(votes) if label in winners)
        confidence = sum(score for name, score in votes if name == label)/counts[label]
        if label != record['voted_label'] or abs(confidence-record['voted_score']) > 1e-9:
            raise ValueError('Voted label/score mismatch')
        expected = label if confidence >= .5 else '?'
        if record.get('displayed_label') != expected:
            raise ValueError('Low-score display mismatch')
        latency = record.get('first_label_ms')
        if key not in first_tracks:
            measured = 1000*(checked_number(record['ui_applied_monotonic_s'])-
                             checked_number(record['first_seen_monotonic_s']))
            if measured < 0 or abs(checked_number(latency)-measured) > 1e-6:
                raise ValueError('First observed-to-applied latency mismatch')
            first_tracks.add(key)
        elif latency is not None:
            raise ValueError('Duplicate first-label latency')
    return len(first_tracks)


def metrics(result):
    records = result['records']
    count = check_votes(records)
    telemetry = result['telemetry']
    if not records or not telemetry:
        raise ValueError('No captures or telemetry')
    for entry in telemetry:
        decode_processing_status(entry.get('processing_status'))
        if (not 30 <= checked_number(entry['temperature_c']) < 85 or
                checked_number(entry['rx_rssi_dbm']) > -30 or
                entry.get('tx_atten_mdb') != [89750, 89750]):
            raise ValueError('Safety/continuity telemetry failed')
    latency = [r['first_label_ms'] for r in records if r['first_label_ms'] is not None]
    truth_hz = result.get('fm_truth_hz', [])
    if any(not math.isfinite(f) or abs(f-result['requested_lo_hz']) >= 1920000 for f in truth_hz):
        raise ValueError('Invalid independent truth frequency')
    truth = [r for r in records if any(abs(r['frequency_hz']-f) <= 25000 for f in truth_hz)]
    fm = sum(r['displayed_label'] == 'FM' for r in truth)/len(truth) if truth else None
    steady = [r for r in truth if len(r['votes']) == 5]
    steady_fm = sum(r['displayed_label'] == 'FM' for r in steady)/len(steady) if steady else None
    values = dict(tracks=count, captures=len(records), telemetry_points=len(telemetry),
                  observed_to_applied_median_ms=float(np.median(latency)),
                  observed_to_applied_max_ms=max(latency),
                  latency_scope='First PS CFAR observation to LCD APPLIED; earlier RF detection unmeasured',
                  display_fps_median=float(np.median([checked_number(e['display_fps']) for e in telemetry])),
                  processing_status_counts=dict(Counter(str(e['processing_status']) for e in telemetry)),
                  processing_fault_mask=3,
                  fm_truth_hz=truth_hz, fm_truth_captures=len(truth),
                  fm_displayed_fraction=fm,
                  fm_full_five_vote_captures=len(steady),
                  fm_full_five_vote_displayed_fraction=steady_fm,
                  vote_scope='All rolling votes and full-five-vote results reported separately',
                  elapsed_s=checked_number(result['elapsed_total_s']))
    complete = (result['status'] == 'completed' and not result.get('stopped_by_signal') and
                values['elapsed_s'] >= result['duration_requested_s'] >= 120)
    # Explicitly retain the differing original and final-plan latency gates.
    original = dict(complete_120s=complete,
                    observed_latency_under_500ms=values['observed_to_applied_median_ms'] < 500,
                    formal_98mhz_truth_fm_80pct=(fm >= .8 if fm is not None and
                                               result['requested_lo_hz'] == 98000000 else None))
    final = dict(complete_120s=complete,
                 observed_latency_at_most_1s=values['observed_to_applied_median_ms'] <= 1000,
                 known_fm_displayed_80pct=steady_fm >= .8 if steady_fm is not None else None,
                 median_display_fps_at_least_30=values['display_fps_median'] >= 30)
    values.update(original_x5_checks=original, final_y2_checks=final,
                  automated_y2_status=('FAIL' if any(v is False for v in final.values()) else
                                       'NOT_EVALUATED' if any(v is None for v in final.values()) else
                                       'PASS_AUTOMATED_AWAITING_VISUAL'))
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True, help='Existing x5_formal_rN or x5_station_rN')
    args = parser.parse_args()
    if args.tag not in {'x5_%s_r%d' % (mode, n) for mode in ('formal', 'station') for n in (1, 2, 3)}:
        parser.error('Invalid measurement tag')
    directory = ROOT/'board/measurements'/args.tag
    receipt_path = directory.with_name(args.tag+'_execution.json')
    receipt = verified(receipt_path)
    result = verified(directory/'result.json')
    if receipt['status'] != 'PASS_EXECUTION' or sha(directory/'result.json') != receipt['result_sha256']:
        raise ValueError('Execution receipt does not establish successful capture')
    checks = verify_captures(directory, result)
    if checks != receipt['capture_checks']:
        raise ValueError('Capture checks changed since retrieval')
    values = metrics(result)
    value = dict(recorded_at_pc=datetime.now(timezone.utc).isoformat(),
                 schema='x5-y2-independent-board-analysis-v1',
                 status=values['automated_y2_status'], metrics=values,
                 human_visual='PENDING', packet_checks=len(checks),
                 source_sha256={Path(__file__).relative_to(ROOT).as_posix(): sha(Path(__file__))},
                 input_sha256={p.relative_to(ROOT).as_posix(): sha(p) for p in
                               (receipt_path, directory/'result.json')})
    output = directory.with_name(args.tag+'_analysis.json')
    write_evidence(output, value)
    print(json.dumps(value, indent=2))


if __name__ == '__main__':
    main()
