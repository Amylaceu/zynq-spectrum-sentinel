"""Generate deterministic phase/FIR vectors; never access hardware or RF."""
import argparse
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from x2_transport import sha, write_evidence


def signed24(value):
    return (int(value)+(1 << 23)) % (1 << 24)-(1 << 23)


def phase_word(i, q, table):
    x, y = int(i) << 16, int(q) << 16
    angle = 0
    if x < 0:
        x, y, angle = -x, -y, -(1 << 23) if y < 0 else (1 << 23)
    for n, step in enumerate(table):
        if y > 0:
            x, y, angle = x+(y >> n), y-(x >> n), angle+int(step)
        elif y < 0:
            x, y, angle = x-(y >> n), y+(x >> n), angle-int(step)
    return signed24(angle)


def hexfile(path, values, bits):
    mask = (1 << bits)-1
    path.write_text(''.join(format(int(v) & mask, '0%dx' % ((bits+3)//4))+'\n'
                            for v in values), encoding='ascii')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    table = [round(math.atan(2**-n)/(2*math.pi)*2**24) for n in range(20)]
    n = np.arange(161)-80
    taps = 2*(17000/480000)*np.sinc(2*(17000/480000)*n)*np.hamming(161)
    taps = np.rint(taps/taps.sum()*2**17).astype(np.int64)
    taps[80] += 2**17-int(taps.sum())
    beta = round((1-math.exp(-1/(48000*75e-6)))*2**18)
    if beta != 63579:
        raise ValueError('RTL deemphasis coefficient mismatch')
    count = 8193
    t = np.arange(count)/480000
    # Both quadrants, carrier winding and positive/negative deviations.
    frequency = 75000+20000*np.sin(2*np.pi*1000*t)
    angle = 2*np.pi*np.cumsum(frequency)/480000
    iq = np.rint(24000*np.column_stack((np.cos(angle), np.sin(angle)))).astype(np.int64)
    iq[0:5] = [(0, 0), (32767, 0), (0, 32767), (-32768, 0), (0, -32768)]
    iq[299:301] = 0  # zero invalidates the pair; never compute a made-up phase.
    fcw = round(75000/480000*2**32)
    phases, expected = [], []
    previous, have_previous = 0, False
    float_errors = []
    for i, q in iq:
        current = phase_word(i, q, table)
        phases.append(signed24(current-previous-(fcw >> 8)) if have_previous and (i or q) else 0)
        if i or q:
            exact = math.atan2(int(q), int(i))/(2*math.pi)*2**24
            float_errors.append(abs(signed24(round(current-exact))))
        previous, have_previous = current, bool(i or q)
    deemphasis = 0
    for index in range(0, count, 10):
        total = sum(int(taps[k])*phases[index-k] for k in range(min(index+1, 161)))
        filtered = total >> 17
        deemphasis += ((filtered-deemphasis)*beta) >> 18
        expected.append(max(-8388608, min(8388607, (deemphasis*41943) >> 16)))
    if max(float_errors) > 16:
        raise ValueError('CORDIC differs from independent atan2')
    audio = np.asarray(expected, dtype=np.float64)/2**23
    keep = audio[100:]
    target = .2*(20000/75000)/math.sqrt(1+(2*np.pi*1000*75e-6)**2)
    amplitude = math.sqrt(2)*np.std(keep)
    peak = int(np.argmax(abs(np.fft.rfft(keep*np.hanning(len(keep))))))
    peak_hz = peak*48000/len(keep)
    if abs(amplitude/target-1) > .04 or abs(peak_hz-1000) > 80:
        raise ValueError('Independent FM frequency/amplitude gate failed')
    words = [((int(q) & 65535) << 16) | (int(i) & 65535) for i,q in iq]
    for name, values, bits in (
        ('y3_atan.hex', table, 26), ('y3_audio_fir.hex', taps, 18),
        ('y3_fm_input.hex', words, 32), ('y3_phase_expected.hex', phases, 24),
        ('y3_audio_expected.hex', expected, 32)):
        hexfile(args.out/name, values, bits)
    write_evidence(args.out/'vectors.json', dict(
        status='PASS_GOLDEN', scope='PC golden only; no RTL/board acceptance',
        input_samples=count, output_samples=len(expected), fcw=fcw,
        zero_samples=int(np.count_nonzero(np.all(iq==0, axis=1))),
        deemphasis_beta=beta, cordic_max_phase_lsb_error=max(float_errors),
        audio_peak_hz=peak_hz, audio_amplitude=amplitude, expected_amplitude=target,
        sources_sha256={Path(__file__).relative_to(ROOT).as_posix(): sha(Path(__file__))},
        vector_sha256={p.name: sha(p) for p in args.out.glob('*.hex')}))
    print('Y3_FM_GOLDEN_PASS samples=%d audio=%d' % (count, len(expected)))


if __name__ == '__main__':
    main()
