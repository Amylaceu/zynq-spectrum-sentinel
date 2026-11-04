"""Extend preserved FM-r3 stimuli for production FIFO depth/prefill validation.

This is a new integration scope, not a fourth standalone FM component round.
The r3 FM golden files and their evidence remain unchanged.
"""
import math
from pathlib import Path

import numpy as np

from gen_y3_fm_vectors import ROOT, hexfile, phase_word, signed24
from x2_transport import sha, write_evidence


def main():
    out = ROOT / 'build/work/y3_sink_vectors_r3'
    out.mkdir(exist_ok=False)
    frozen = ROOT / 'build/work/y3_fm_vectors_r3'
    table = [int(x, 16) for x in (frozen/'y3_atan.hex').read_text().split()]
    taps = [int(x, 16) for x in (frozen/'y3_audio_fir.hex').read_text().split()]
    taps = [x-(1 << 18) if x & (1 << 17) else x for x in taps]
    count = 49153
    t = np.arange(count)/480000
    phase = 2*np.pi*np.cumsum(75000+20000*np.sin(2*np.pi*1000*t))/480000
    iq = np.rint(24000*np.column_stack((np.cos(phase), np.sin(phase)))).astype(np.int64)
    iq[:5] = [(0, 0), (32767, 0), (0, 32767), (-32768, 0), (0, -32768)]
    iq[299:301] = 0
    phases = []
    previous, valid = 0, False
    for i, q in iq:
        angle = phase_word(i, q, table)
        phases.append(signed24(angle-previous-0x280000) if valid and (i or q) else 0)
        previous, valid = angle, bool(i or q)
    expected, deemphasis = [], 0
    for n in range(0, count, 10):
        value = sum(taps[k]*phases[n-k] for k in range(min(n+1, 161))) >> 17
        deemphasis += ((value-deemphasis)*63579) >> 18
        expected.append(max(-8388608, min(8388607, (deemphasis*41943) >> 16)))
    # The prefix must reproduce the already accepted FM-r3 golden exactly.
    old = [int(x, 16) for x in (frozen/'y3_audio_expected.hex').read_text().split()]
    if [x & 0xffffffff for x in expected[:len(old)]] != old:
        raise ValueError('Golden prefix differs from preserved FM r3')
    hexfile(out/'y3_fm_input.hex', [(int(i)&65535)|((int(q)&65535)<<16) for i,q in iq], 32)
    hexfile(out/'y3_audio_expected.hex', expected, 32)
    for name in ('y3_atan.hex', 'y3_audio_fir.hex'):
        (out/name).write_bytes((frozen/name).read_bytes())
    write_evidence(out/'vectors.json', dict(status='PASS_GOLDEN', input_samples=count,
        output_samples=len(expected), pcm_depth=8192, prefill=4096,
        prefix_matches_fm_r3=True, clock_simulation='audio clock +80ppm vs ideal; no physical claim',
        source_sha256={Path(__file__).relative_to(ROOT).as_posix(): sha(Path(__file__))},
        vector_sha256={p.name: sha(p) for p in out.glob('*.hex')}))
    print('Y3_SINK_GOLDEN_PASS input=%d pcm=%d' % (count, len(expected)))


if __name__ == '__main__':
    main()
