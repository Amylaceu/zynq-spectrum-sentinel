"""Check native-complex Gardner arithmetic against the frozen round-2 loop.

Uses generated captures with independent seeds; no test/validation selection.
This comparison checks synchronization arithmetic, not classification quality.
"""
import importlib.util
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim.golden.siggen import gen_mod
from src.ps.sentinel.amc.fine import gardner, rrc
from x2_transport import sha, write_evidence


def main():
    reference = ROOT/'build/work/x4_pc_r2/source/src/ps/sentinel/amc/fine.py'
    spec = importlib.util.spec_from_file_location('src.ps.sentinel.amc._r2_sync', reference)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = []
    for sps in (4, 7, 8, 13, 16):
        for label in ('QPSK', '8PSK', '16QAM', '64QAM'):
            iq = gen_mod(label, 4096, sps, fs=480000, seed=941+sps,
                         cfo_hz=137, phase=.38)
            matched = np.convolve(iq.astype(np.complex128), rrc(sps), mode='same')
            expected = module.gardner(matched, float(sps))
            actual = gardner(matched, float(sps))
            np.testing.assert_allclose(actual, expected, rtol=1e-10, atol=1e-10)
            rows.append(dict(sps=sps, label=label, count=len(actual),
                             max_absolute_error=float(np.max(np.abs(actual-expected)))))
    result = dict(step='X4', mode='independent_generated_sync_arithmetic',
                  status='PASS', rows=rows, source_sha256={
                      p.relative_to(ROOT).as_posix(): sha(p) for p in
                      (Path(__file__), reference, ROOT/'src/ps/sentinel/amc/fine.py',
                       ROOT/'sim/golden/siggen.py')})
    write_evidence(ROOT/'board/measurements/x4_sync_arithmetic_r3.json', result)
    print('SYNC_ARITHMETIC_PASS', len(rows))


if __name__ == '__main__':
    main()
