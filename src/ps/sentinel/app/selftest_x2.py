"""Finite v1c tone and exact replay checks before any new RF measurement."""
import argparse
import hashlib
from pathlib import Path

import numpy as np

from .monitor_x2 import checked_bundle, drain
from .runtime_x2 import SessionX2
from .selftest_v1 import finite_frame, bin_error
from ..artifacts import atomic_json, atomic_write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bit', required=True)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--references', required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists() or args.out.with_suffix('.npz').exists():
        parser.error('Preserve prior self-test')
    acceptance = checked_bundle(args.bit)
    files = [args.references/name for name in ('in_axis32.hex', 'exp_power_shifted.hex')]
    inputs, golden = [np.array([int(x, 16) for x in path.read_text().split()],
                              dtype=np.uint32).reshape(4, 2048) for path in files]
    result = dict(status='started', RF_TX_requested=False, rf_initialized=False,
                  boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                  artifacts_sha256=acceptance['artifacts_sha256'], tests=[],
                  reference_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    try:
        atomic_json(args.out, result)
        with SessionX2(args.bit, source='test', rate=30720000) as session:
            hw = session.hw
            hw.enable_processing(average_shift=0)
            hw.lcd.set_bus_phase(3)
            hw.lcd.enable()
            hw.perf.clear()
            hw.perf.arm()
            single, targets, perf = finite_frame(hw, 'test', rate=30720000)
            peak = int(np.argmax(single))
            result['tests'].append(dict(name='single_tone', peak_bin=peak, error_bins=bin_error(peak, 1088)))
            if bin_error(peak, 1088) > 1:
                raise AssertionError('Single-tone peak exceeds one bin')
            drain(hw)
            triple, targets, perf = finite_frame(hw, 'test', (-300, 64, 300),
                                                 (4096, 4096, 4096), rate=30720000)
            peaks = [t.peak_bin for t in targets]
            result['tests'].append(dict(name='three_tones', peaks=peaks))
            if len(peaks) != 3 or any(min(bin_error(x, y) for x in peaks) > 1 for y in (724, 1088, 1324)):
                raise AssertionError('Three-tone target mismatch')
            drain(hw)
            actual = []
            for index in range(4):
                power, _, perf = finite_frame(hw, 'replay', replay=inputs[index], rate=30720000)
                actual.append(power)
                differences = int(np.count_nonzero(power != golden[index]))
                result['tests'].append(dict(name='golden_replay', frame=index, words=2048, mismatches=differences))
                result['stream'] = drain(hw).__dict__
                atomic_json(args.out, result)
                if differences:
                    raise AssertionError('Replay power differs from golden reference')
            if result['stream']['frame_drop']:
                raise AssertionError('Finite isolated frames must not be dropped')
            archive = args.out.with_suffix('.npz')
            atomic_write(archive, lambda stream: np.savez_compressed(stream, power=np.stack(actual),
                golden=golden, input_words=inputs, single_tone_power=single, triple_tone_power=triple))
            result.update(raw_archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), perf=perf.__dict__)
        result['status'] = 'passed'
    except BaseException as error:
        result.update(status='failed', error=str(error))
        raise
    finally:
        atomic_json(args.out, result)
    print('X2_FINITE_SELFTEST_PASS', flush=True)


if __name__ == '__main__':
    main()
