"""Independently verify retrieved v1c powers against the frozen local vectors."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

from x2_transport import ROOT, sha, verified, write_evidence

sys.path.insert(0, str(ROOT/'src/ps'))
from sentinel.drivers.stream_x2 import StreamSnapshot


def verify_tone_peaks(single, triple):
    """Check global separated maxima, with the board's one-bin tolerance."""
    def distance(a, b):
        return min((a-b) % 2048, (b-a) % 2048)
    if distance(int(np.argmax(single)), 1088) > 1:
        raise ValueError('Single-tone peak differs')
    remaining = np.array(triple, dtype=np.float64, copy=True)
    peaks = []
    for _ in range(3):
        peak = int(np.argmax(remaining))
        peaks.append(peak)
        remaining[[(peak+i) % 2048 for i in range(-4, 5)]] = -np.inf
    if any(min(distance(x, y) for x in peaks) > 1 for y in (724, 1088, 1324)):
        raise ValueError('Three-tone peak differs')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--measurement', type=Path, required=True)
    args = parser.parse_args()
    path = args.measurement.resolve()
    data = verified(path)
    execution_path = path.with_name(path.stem+'_execution.json')
    execution = verified(execution_path)
    archive = path.with_suffix('.npz')
    if (data['status'] != 'passed' or data['RF_TX_requested'] is not False
            or data['rf_initialized'] is not False or execution['status'] != 'PASS_EXECUTION'
            or execution['result_sha256'] != sha(path) or sha(archive) != data['raw_archive_sha256']
            or verified_digest(archive) != sha(archive)
            or execution['archive_sha256'] != sha(archive)
            or execution['boot_id_before'] != data['boot_id']
            or execution['postflight']['boot_id'] != data['boot_id']
            or execution['postflight']['status'] != 'PASS'):
        raise ValueError('Self-test execution/boot/archive mismatch')
    refs = ROOT/'data/reference/spectrum'
    arrays = []
    for name in ('in_axis32.hex', 'exp_power_shifted.hex'):
        reference = refs/name
        if data['reference_sha256'][name] != sha(reference):
            raise ValueError('Reference hash differs: '+name)
        arrays.append(np.array([int(x, 16) for x in reference.read_text().split()],
                               dtype=np.uint32).reshape(4, 2048))
    inputs, golden = arrays
    with np.load(archive, allow_pickle=False) as raw:
        for name, expected in (('power', golden), ('golden', golden), ('input_words', inputs)):
            if not np.array_equal(raw[name], expected):
                raise ValueError('Bit-exact self-test failed: '+name)
        verify_tone_peaks(raw['single_tone_power'], raw['triple_tone_power'])
    stream = StreamSnapshot(**data['stream'])
    stream.require_lossless()
    if stream.frame_drop or stream.frames_in != 6 or stream.frames_out != 6:
        raise ValueError('Finite-frame conservation failed')
    result = dict(status='PASS', measurement_sha256=sha(path),
                  execution_sha256=sha(execution_path), archive_sha256=sha(archive),
                  exact_replay_words=8192, finite_frames=6, analyzer_sha256=sha(Path(__file__)))
    write_evidence(path.with_name(path.stem+'_acceptance.json'), result)
    print(json.dumps(result, indent=2))


def verified_digest(path):
    return Path(str(path)+'.sha256').read_text().split()[0]


if __name__ == '__main__':
    main()
