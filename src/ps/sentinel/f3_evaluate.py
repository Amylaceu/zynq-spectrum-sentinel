"""Pure post-capture noise evaluation; no hardware access or model fitting."""
import numpy as np
from .amc.contract import COARSE_MAP


def add_noise(iq, snr_db, rng):
    """Reference is measured total IQ power, including intrinsic receiver noise.

    Therefore this parameter is NOT the effective RF signal-to-noise ratio.
    The injected noise has exact sample power; receiver noise is not subtracted.
    """
    x = np.asarray(iq, dtype=np.complex128)
    if x.ndim != 2 or not np.isfinite(x).all() or not np.isfinite(snr_db):
        raise ValueError('Expected finite batch IQ and noise reference')
    power = np.mean(abs(x)**2, axis=1, keepdims=True)
    if np.any(power <= 0):
        raise ValueError('Zero-power capture')
    noise = rng.normal(size=x.shape)+1j*rng.normal(size=x.shape)
    noise *= np.sqrt(power / (10**(snr_db/10)*np.mean(abs(noise)**2, axis=1, keepdims=True)))
    return (x+noise).astype(np.complex64)


def confusion(labels, predicted, classes):
    y, p = np.asarray(labels), np.asarray(predicted)
    if y.shape != p.shape or y.ndim != 1 or y.dtype.kind not in 'iu' or p.dtype.kind not in 'iu':
        raise ValueError('Expected aligned integer labels')
    if np.any(y < 0) or np.any(p < 0) or np.any(y >= classes) or np.any(p >= classes):
        raise ValueError('Class outside label contract')
    counts = np.zeros((classes, classes), dtype=np.int64)
    np.add.at(counts, (y, p), 1)
    return counts


def scores(labels, predicted):
    matrix = confusion(labels, predicted, 10)
    mapping = np.asarray(COARSE_MAP)
    coarse = confusion(mapping[labels], mapping[predicted], 8)
    return dict(accuracy_10=float(np.trace(matrix)/matrix.sum()),
                accuracy_8=float(np.trace(coarse)/coarse.sum()),
                confusion_10=matrix.tolist(), confusion_8=coarse.tolist())
