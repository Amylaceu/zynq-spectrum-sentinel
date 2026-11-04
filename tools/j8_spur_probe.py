"""Bounded F1-path receive-only LO-offset check; never asserts a physical source.

Run on the board only after the resident service has stopped. Three measured
power frames at each of two LO offsets distinguish fixed-RF peaks from features
which follow the receiver baseband. An ambiguous result remains unclassified.
"""
import argparse
from pathlib import Path
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--frequencies', nargs='+', type=int, required=True)
    args = parser.parse_args()
    if len(args.frequencies) > 5 or any(not 300000000 <= v <= 420000000 for v in args.frequencies):
        parser.error('At most five observed 300–420 MHz candidates')
    sys.path.insert(0, str(args.release/'ps'))
    import numpy as np
    from sentinel.app.features_j6 import FeatureBackend, db
    from sentinel.release_support import verify_release, write_result, sha
    verify_release(args.release)
    args.out.mkdir(parents=True, exist_ok=False)
    backend = FeatureBackend(args.release, args.out, hostlink_bind='192.168.2.99')
    result = dict(status='RUNNING', source='F1_LIVE_RF_PATH', tx_requested=False,
                  inference_scope='LO translation alone cannot identify a physical emitter', candidates=[])
    default = None
    try:
        backend.start()
        default = dict(backend.config)
        for index, frequency in enumerate(args.frequencies):
            trials = []
            for side, offset in enumerate((-600000, 600000)):
                backend.restore()
                backend.config['lo_hz'] = frequency+offset
                backend.radio.configure(frequency+offset, 3840000, backend.config['rf_bandwidth_hz'])
                started = backend.feature('F1')
                if started['status'] != 'READY': raise RuntimeError(str(started))
                frames = []
                for _ in range(3):
                    backend.safety(); time.sleep(.1)
                    power, _ = backend.capture(); frames.append(power)
                measured = np.median(np.stack(frames), axis=0)
                lo = backend.radio.rx_lo
                axis = lo+(np.arange(2048)-1024)*1875.
                near = np.flatnonzero(abs(axis-frequency) <= 25000)
                peak = int(near[np.argmax(measured[near])])
                values = db(measured)
                usable = np.r_[128:1020, 1029:1920]
                dominant = int(usable[np.argmax(measured[usable])])
                path = args.out/('candidate_%d_lo_%d.npz' % (index, side))
                np.savez_compressed(path, power=np.stack(frames), frequency_hz=axis)
                trials.append(dict(lo_hz=lo, peak_hz=float(axis[peak]),
                    prominence_db=float(values[peak]-np.median(values[usable])),
                    dominant_bin=dominant, dominant_hz=float(axis[dominant]),
                    dominant_prominence_db=float(values[dominant]-np.median(values[usable])),
                    file=path.name, sha256=sha(path), readback=backend.readback()))
            fixed_rf = all(t['prominence_db'] >= 12 for t in trials) and abs(trials[0]['peak_hz']-trials[1]['peak_hz']) <= 10000
            follows_lo = (all(t['dominant_prominence_db'] >= 12 for t in trials)
                          and abs(trials[0]['dominant_bin']-trials[1]['dominant_bin']) <= 2)
            assessment = ('FIXED_RF_SOURCE_UNDETERMINED' if fixed_rf else
                          'SUSPECT_RECEIVER_BASEBAND_SPUR' if follows_lo else 'UNDETERMINED')
            result['candidates'].append(dict(frequency_hz=frequency, trials=trials,
                assessment=assessment, suspect_internal_spur=bool(follows_lo and not fixed_rf)))
            write_result(args.out/'result.json', result)
        result['status'] = 'MEASURED'
    except Exception as error:
        result.update(status='FAIL', error=repr(error))
        raise
    finally:
        if default is not None:
            backend.config = default
            backend.radio.configure(default['lo_hz'], 3840000, default['rf_bandwidth_hz'])
            result['restored'] = backend.restore()
        backend.close()
        result['closed'] = backend.closed
        write_result(args.out/'result.json', result)


if __name__ == '__main__': main()
