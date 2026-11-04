"""Compare raw ADC and pre-NCO PFB snapshots, without RF or playback.

Pilot prominence is evidence of a possible FM stereo pilot, NOT audio SNR or
station identity. Snapshot edges are discarded; separate blocks stay separate.
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import lfilter, welch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src/ps'), str(ROOT)]
from sentinel.fm_receive import demodulate_chunk
from sim.golden.pfb import pfb_os2
from x2_transport import sha, verified, write_evidence


def read_signed_hex(path, bits):
    values = np.array([int(s, 16) for s in path.read_text().split()], dtype=np.int64)
    return (values+(1 << (bits-1))) % (1 << bits)-(1 << (bits-1))


def channelize(iq, taps, signed_channel=-1, rate=3840000):
    """Causal selected PFB channel, equivalent to the float polyphase model."""
    n = np.arange(len(iq))
    return lfilter(taps/2**17, 1, iq*np.exp(-2j*np.pi*signed_channel*n/16))[::8]


def discriminator_metrics(iq, residual_hz, rate=480000, trim=256):
    iq = np.asarray(iq)
    frequency = np.angle(iq[1:]*iq[:-1].conj())*rate/(2*np.pi)-residual_hz
    steady = frequency[trim:-trim]
    f, p = welch(steady, rate, nperseg=min(16384, len(steady)))
    pilot = (f >= 18500) & (f <= 19500)
    near = ((f >= 17000) & (f <= 21000)) & ~pilot
    peak = np.flatnonzero(pilot)[np.argmax(p[pilot])]
    return dict(iq_rms=float(np.sqrt(np.mean(abs(iq[trim:-trim])**2))),
                zero_fraction=float(np.mean(iq == 0)),
                discriminator_dc_hz=float(np.mean(steady)),
                discriminator_std_hz=float(np.std(steady)),
                large_excursion_fraction=float(np.mean(abs(steady-np.median(steady)) > 150000)),
                pilot_frequency_hz=float(f[peak]),
                pilot_prominence_db=float(10*np.log10(max(p[peak], 1e-30)/max(np.median(p[near]), 1e-30))))


def audio_rtl_math(iq, residual_hz, fir):
    """Floating approximation of current FIR/deemphasis/gain, not bit-exact RTL."""
    frequency = np.r_[0., np.angle(iq[1:]*iq[:-1].conj())*480000/(2*np.pi)-residual_hz]
    lowpass = lfilter(fir/2**17, 1, frequency)[::10]
    beta = 63579/2**18
    deemphasized = lfilter([beta], [1, -(1-beta)], lowpass)
    return deemphasized*(41943/65536)/240000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    taps_path = ROOT/'src/rtl/pfb/x5_pfb_coeff.hex'
    fir_path = ROOT/'src/rtl/audio_y3/rom/y3_audio_fir.hex'
    taps, fir = read_signed_hex(taps_path, 18), read_signed_hex(fir_path, 18)
    result = dict(status='OFFLINE_DIAGNOSTIC', audio_acceptance='NOT_TESTED',
        limitation='Pilot prominence is not SNR; snapshots are gapped, not concurrent pairs.',
        sources_sha256={p.relative_to(ROOT).as_posix(): sha(p) for p in
                        (Path(__file__), taps_path, fir_path, ROOT/'src/ps/sentinel/fm_receive.py')},
        historical=[], current=[])
    historical = ROOT/'data/captured/fm_diagnostic/fm_95800000_round3.sigmf-data'
    meta_path = historical.with_suffix('.sigmf-meta')
    meta = json.loads(meta_path.read_text())
    result['historical_source_sha256'] = sha(historical)
    result['historical_meta_sha256'] = sha(meta_path)

    def analyze_raw(raw, label, lo):
        x = (raw[:, 0].astype(float)+1j*raw[:, 1])/32768
        y = channelize(x, taps)
        z = pfb_os2(x[:8192], taps)[:, 15]
        error = float(np.max(abs(y[:len(z)]-z)))
        if error > 1e-9:
            raise ValueError('Selected-channel shortcut differs from polyphase reference')
        sw, metrics, _, _ = demodulate_chunk(x, 3840000, lo, 95800000)
        pcm = audio_rtl_math(y, 95800000-(lo-240000), fir)
        # Retain actual mathematical gain; do not normalize noise into speech.
        wavfile.write(args.out/(label+'_rtl_math.wav'), 48000,
                      np.rint(np.clip(pcm[960:], -1, 1)*32767).astype('<i2'))
        wavfile.write(args.out/(label+'_software.wav'), 48000,
                      np.rint(np.clip(sw/240000*(41943/65536), -1, 1)*32767).astype('<i2'))
        return dict(label=label, float_pfb_shortcut_max_error=error,
                    software=metrics, pfb=discriminator_metrics(y, 95800000-(lo-240000)),
                    rtl_math_pcm_dc=float(np.mean(pcm[960:])),
                    rtl_math_pcm_ac_rms=float(np.std(pcm[960:])))

    for block in (0, 8):
        capture_meta = meta['captures'][block]
        raw = np.fromfile(historical, dtype='<i2', count=2*1048576,
                          offset=capture_meta['core:sample_start']*4).reshape(-1, 2)
        result['historical'].append(analyze_raw(raw, 'historical_%02d'%block, capture_meta['core:frequency']))
    if args.capture:
        receipt = verified(args.capture/'result.json')
        result['current_receipt_sha256'] = sha(args.capture/'result.json')
        for c in receipt['captures']:
            path = args.capture/c['file']
            if sha(path) != c['sha256']:
                raise ValueError('Snapshot hash mismatch')
            with np.load(path, allow_pickle=False) as snap:
                if c['kind'] == 'raw_adc':
                    raw = snap['raw']
                    row = analyze_raw((raw[:, :2].astype(np.int32)*16).astype('<i2'),
                                      path.stem, receipt['actual_lo_hz'])
                    row.update(kind='raw_adc', adc_min=int(raw.min()), adc_max=int(raw.max()),
                               outside_signed12_fraction=float(np.mean((raw < -2048) | (raw > 2047))))
                else:
                    signed = c['channel'] if c['channel'] < 8 else c['channel']-16
                    row = dict(kind='pfb', file=c['file'], channel=c['channel'],
                               metrics=discriminator_metrics(snap['iq'],
                                  95800000-(receipt['actual_lo_hz']+signed*240000)))
                result['current'].append(row)
    result['wav_sha256'] = {p.name: sha(p) for p in args.out.glob('*.wav')}
    write_evidence(args.out/'analysis.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
