"""Strict complete-vector comparison for RTL outputs and fixed-point references."""
import argparse
import json
from pathlib import Path
import numpy as np


def load(path, bits):
    if path.suffix == '.npy':
        values = np.load(path, allow_pickle=False).reshape(-1)
        if not np.issubdtype(values.dtype, np.integer):
            raise ValueError('Reference must contain integer words')
        return values.astype(np.int64)
    words = []
    for line in path.read_text(encoding='ascii').splitlines():
        for token in line.split('//', 1)[0].split():
            value = int(token, 16)
            if bits:
                if value >= 1 << bits:
                    raise ValueError('Hex word exceeds declared width')
                if value & (1 << (bits-1)):
                    value -= 1 << bits
            words.append(value)
    return np.array(words, dtype=np.int64)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exp', type=Path, required=True)
    parser.add_argument('--got', type=Path, required=True)
    parser.add_argument('--mode', choices=('exact', 'sqnr'), default='exact')
    parser.add_argument('--bits', type=int, choices=range(1, 64))
    parser.add_argument('--min-sqnr', type=float, default=70)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    expected, actual = load(args.exp, args.bits), load(args.got, args.bits)
    if len(expected) != len(actual) or len(expected) == 0:
        raise ValueError('Output must contain every expected word exactly once; counts differ or empty')
    error = actual.astype(np.float64) - expected.astype(np.float64)
    bad = np.flatnonzero(actual != expected)
    signal, noise = float(np.dot(expected.astype(float), expected.astype(float))), float(error @ error)
    sqnr = float('inf') if noise == 0 else (10*np.log10(signal/noise) if signal else float('-inf'))
    passed = not len(bad) if args.mode == 'exact' else sqnr >= args.min_sqnr
    result = dict(status='passed' if passed else 'failed', mode=args.mode,
                  compared_words=len(actual), mismatch_words=len(bad),
                  max_abs_error=float(np.max(np.abs(error))),
                  first_mismatch=int(bad[0]) if len(bad) else None,
                  sqnr_db=float(sqnr) if np.isfinite(sqnr) else str(sqnr),
                  discarded_expected_words=0, discarded_actual_words=0)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_bytes((json.dumps(result, indent=2)+'\n').encode())
    print(json.dumps(result))
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
