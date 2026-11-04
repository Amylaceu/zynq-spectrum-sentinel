"""Independently verify N4 raw captures against the repository golden vectors."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(result_path, reference_dir, bit_path):
    result = json.loads(result_path.read_text(encoding='utf-8-sig'))
    archive_path = result_path.with_suffix('.npz')
    require(result.get('status') == 'passed', 'Board selftest did not pass')
    require(result.get('RF_TX_requested') is False, 'Unexpected RF transmit request')
    require(result.get('bit_sha256') == sha256(bit_path), 'Board/local bit hashes differ')
    require(result.get('raw_archive_sha256') == sha256(archive_path), 'Archive hash mismatch')
    references = {}
    for name, filename in (('input_words', 'in_axis32.hex'),
                           ('golden', 'exp_power_shifted.hex')):
        path = reference_dir / filename
        references[name] = np.array([int(v, 16) for v in path.read_text().split()],
                                    dtype=np.uint32).reshape(4, 2048)
    with np.load(archive_path, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in
                  ('input_words', 'golden', 'power', 'single_tone_power', 'triple_tone_power')}
    for name, array in arrays.items():
        shape = (2048,) if name.endswith('_tone_power') else (4, 2048)
        require(array.shape == shape and array.dtype == np.dtype('uint32'),
                'Wrong shape or dtype: ' + name)
    require(np.array_equal(arrays['input_words'], references['input_words']),
            'Archived input differs from repository reference')
    require(np.array_equal(arrays['golden'], references['golden']),
            'Archived golden differs from repository reference')
    mismatches = np.count_nonzero(arrays['power'] != references['golden'], axis=1)
    require(not mismatches.any(), 'Replay power differs from repository reference')
    peak = int(np.argmax(arrays['single_tone_power']))
    require(abs(peak - 1088) <= 1, 'Independent single-tone peak failed')
    work = arrays['triple_tone_power'].copy()
    peaks = []
    for _ in range(3):
        index = int(np.argmax(work))
        peaks.append(index)
        work[max(0, index-4):min(2048, index+5)] = 0
    expected = [724, 1088, 1324]
    require(all(abs(a-b) <= 1 for a, b in zip(sorted(peaks), expected)),
            'Independent three-tone peaks failed')
    tests = result.get('tests', [])
    require(len(tests) == 6, 'Expected single/triple and four replay records')
    require(tests[0]['name'] == 'single_tone' and tests[0]['peak_bin'] == peak
            and tests[0]['error_bins'] == abs(peak-1088), 'Inconsistent single-tone record')
    require(tests[1]['name'] == 'three_tones' and tests[1]['target_count'] == 3
            and len(tests[1]['peaks']) == 3
            and all(abs(a-b) <= 1 for a, b in zip(sorted(tests[1]['peaks']), expected)),
            'Three-target CFAR record failed')
    for i, test in enumerate(tests[2:]):
        require(test['name'] == 'golden_replay' and test['frame'] == i
                and test['words'] == 2048 and test['mismatches'] == int(mismatches[i]),
                'Inconsistent replay record')
    require(result['perf']['status'] & 3 == 0, 'Overflow/framing status is set')
    return {
        'status': 'passed',
        'scope': 'N4 finite PL test/replay archive only; RF, visual LCD and sustained throughput remain separate gates',
        'result_sha256': sha256(result_path),
        'archive_sha256': sha256(archive_path),
        'bit_sha256': sha256(bit_path),
        'reference_sha256': {p.name: sha256(p) for p in
                             (reference_dir/'in_axis32.hex', reference_dir/'exp_power_shifted.hex')},
        'replay_compared_words': 8192,
        'mismatches_by_frame': mismatches.tolist(),
        'single_peak_bin': peak,
        'three_peak_bins': sorted(peaks),
        'cfar_target_count': 3,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result', type=Path, default=ROOT/'board/measurements/n4_selftest.json')
    parser.add_argument('--reference', type=Path, default=ROOT/'data/reference/spectrum')
    parser.add_argument('--bit', type=Path, default=ROOT/'board/overlay/sentinel_v1/sentinel_v1.bit')
    parser.add_argument('--out', type=Path, default=ROOT/'board/measurements/n4_selftest_acceptance.json')
    args = parser.parse_args()
    require(not args.out.exists(), 'Preserve existing acceptance; choose another --out')
    result = verify(args.result, args.reference, args.bit)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('N4_SELFTEST_ARCHIVE_ACCEPTANCE_PASS')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
