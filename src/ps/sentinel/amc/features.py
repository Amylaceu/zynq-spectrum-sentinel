"""Shared NumPy frontend, including floating PS HOC (not RTL fixed moments).

Every feature uses received samples only, never true SNR, modulation or sps.
CNN channels preserve short-block IQ means, envelope and phase increments.
The envelope uses uncentred samples so AM carrier information is retained.
"""
import numpy as np

from .contract import CAPTURE_LEN_AMC, FRONTEND_BLOCK


def complex_iq(iq):
    """Accept complex [N]/[B,N], or real IQ [2,N]/[B,2,N]."""
    value = np.asarray(iq)
    if np.iscomplexobj(value):
        z = np.atleast_2d(value).astype(np.complex64)
    else:
        if value.ndim == 2:
            value = value[None]
        if value.ndim != 3 or value.shape[1] != 2:
            raise ValueError('Expected complex IQ or [batch,2,4096]')
        z = value[:, 0].astype(np.float32) + 1j * value[:, 1].astype(np.float32)
    if z.ndim != 2 or z.shape[1] != CAPTURE_LEN_AMC or not np.isfinite(z).all():
        raise ValueError('Exactly 4096 finite IQ points required')
    if np.any(np.mean(np.abs(z)**2, axis=1) <= 0):
        raise ValueError('Zero-power IQ is not a valid target capture')
    return z


def frontend(iq):
    z = complex_iq(iq)
    z = z / np.sqrt(np.mean(np.abs(z)**2, axis=1, keepdims=True))
    env = np.abs(z)
    dc = np.abs(z.mean(axis=1))
    x = z - z.mean(axis=1, keepdims=True)
    x /= np.sqrt(np.mean(np.abs(x)**2, axis=1, keepdims=True)).clip(1e-8)
    power = np.abs(x)**2
    diff = x[:, 1:] * x[:, :-1].conj()
    angle = np.angle(diff)
    m20 = np.mean(x**2, axis=1)
    m40 = np.mean(x**4, axis=1)
    m42 = np.mean(power**2, axis=1)
    c40 = m40 - 3*m20**2
    c42 = m42 - np.abs(m20)**2 - 2
    spectrum = np.abs(np.fft.fft(x, axis=1))**2
    weights = spectrum / spectrum.sum(axis=1, keepdims=True).clip(1e-20)
    frequency = np.fft.fftfreq(CAPTURE_LEN_AMC)
    centroid = np.sum(weights * frequency, axis=1)
    spread = np.sqrt(np.sum(weights * (frequency-centroid[:, None])**2, axis=1))
    values = [dc, env.mean(1), env.std(1), np.mean(env**4, axis=1),
              np.abs(m20), np.abs(c40), c42, np.mean(power**3, axis=1),
              np.abs(np.mean(x**6, axis=1)), np.abs(np.mean(x**8, axis=1)),
              np.mean(angle, axis=1), np.std(angle, axis=1),
              np.mean(angle**2, axis=1), np.mean(angle**4, axis=1),
              np.abs(np.mean(diff, axis=1)), np.std(np.abs(diff), axis=1),
              np.abs(np.mean(np.exp(2j*angle), axis=1)),
              np.abs(np.mean(np.exp(4j*angle), axis=1)),
              spread, np.max(weights, axis=1),
              -np.sum(weights*np.log(weights.clip(1e-20)), axis=1),
              np.mean(env < .5, axis=1), np.quantile(env, .1, axis=1),
              np.quantile(env, .9, axis=1)]
    features = np.stack(values, axis=1).astype(np.float32)
    # Signed log controls high-order outliers without losing C42's sign.
    features = np.sign(features)*np.log1p(np.abs(features))
    phase = np.pad(angle, ((0, 0), (1, 0))) / np.pi
    channels = np.stack((x.real, x.imag, env, phase), axis=1)
    channels = channels.reshape(len(z), 4, -1, FRONTEND_BLOCK).mean(axis=-1)
    if not np.isfinite(features).all():
        raise ValueError('Nonfinite moments')
    return channels.astype(np.float32), features
