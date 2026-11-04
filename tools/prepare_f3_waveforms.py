"""Seeded 480kSPS signals, x8 interpolation, TX1 at +240kHz; no RF access."""
import hashlib
import sys
from pathlib import Path
import numpy as np
from scipy.signal import resample_poly
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'src/ps'))
from sim.golden.siggen import gen_mod
from sentinel.amc.contract import CLASSES
sys.path.insert(0, str(ROOT/'tools'))
from x2_transport import write_evidence, sha


def main():
    out = ROOT/'data/reference/f3_ota'
    out.mkdir(exist_ok=False)
    record = dict(schema='F3-TX1-native12-left16-v1', fs_base_hz=480000,
                  fs_tx_hz=3840000, carrier_offset_hz=240000, periodic_base_samples=32768,
                  scope='Cyclic waveform, captures may overlap/repeat; not independent waveform trials', waveforms=[])
    for index, label in enumerate(CLASSES):
        seed = 73000+index
        base = gen_mod(label, n=32768, sps=8, fs=480000, seed=seed)
        # Smooth only wrap boundary; retain raw base for reproducible simulation.
        edge = np.ones(len(base))
        edge[:128] = np.sin(np.linspace(0, np.pi/2, 128))**2
        edge[-128:] = edge[:128][::-1]
        x = resample_poly(base*edge, 8, 1)
        x *= np.exp(2j*np.pi*240000*np.arange(len(x))/3840000)
        scale = 1023/max(abs(x.real).max(), abs(x.imag).max())
        words = np.zeros((len(x), 4), dtype='<i2')
        words[:, 0] = np.rint(x.real*scale).astype('<i2')*16
        words[:, 1] = np.rint(x.imag*scale).astype('<i2')*16
        name = 'tx_%02d.npz' % index
        path = out/name
        np.savez_compressed(path, words=words, base=base)
        record['waveforms'].append(dict(label=label, index=index, seed=seed, filename=name,
            sha256=sha(path), words_sha256=hashlib.sha256(words.tobytes()).hexdigest(),
            words_shape=list(words.shape), peak_native=int(abs(words.astype(np.int32)).max()//16)))
    write_evidence(out/'manifest.json', record)
    print('Prepared ten waveforms, manifest SHA256', sha(out/'manifest.json'))


if __name__ == '__main__':
    main()
