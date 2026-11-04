"""Blind PSK/QAM refinement; NumPy only, no ground-truth symbol rate or CFO.

Circular-spectrum rate estimate, Mth-power CFO correction, RRC filtering and
Gardner interpolation produce symbol samples. Thresholds are theoretical HOC
midpoints, not fitted on validation/test labels. Multipath/noise can defeat
these estimators; diagnostics are returned so failures stay inspectable.
"""
import numpy as np

from .contract import AMC_FS
from .features import complex_iq


def estimate_sps(x):
    power = np.abs(x)**2
    spectrum = np.abs(np.fft.rfft((power-power.mean())*np.hanning(len(x))))**2
    lo, hi = int(len(x)/16), int(np.ceil(len(x)/4))+1
    peak = lo+int(np.argmax(spectrum[lo:hi]))
    ratio = float(spectrum[peak]/np.median(spectrum[lo:hi]).clip(1e-12))
    return float(np.clip(len(x)/peak, 4, 16)), ratio


def correct_cfo(x, sps, order):
    # Suppress noisy high-amplitude outliers before taking the Mth power.
    unit = x/np.abs(x).clip(.2)
    transformed = unit**order
    bins = np.fft.fftfreq(len(x))
    spectrum = np.abs(np.fft.fft(transformed*np.hanning(len(x))))**2
    allowed = np.abs(bins) <= .08*order/sps
    index = int(np.argmax(np.where(allowed, spectrum, -1)))
    # Parabolic interpolation reduces residual phase rotation across a capture.
    left, middle, right = np.log(spectrum[[(index-1)%len(x), index, (index+1)%len(x)]].clip(1e-30))
    denominator = left-2*middle+right
    delta = float(np.clip(.5*(left-right)/denominator, -.5, .5)) if abs(denominator) > 1e-15 else 0.
    frequency = float((bins[index]+delta/len(x))/order)
    return x*np.exp(-2j*np.pi*frequency*np.arange(len(x))), frequency


def rrc(sps, beta=.35, span=8):
    half = int(np.ceil(span*sps/2))
    t = np.arange(-half, half+1)/sps
    h = np.empty(len(t))
    zero = np.isclose(t, 0)
    edge = np.isclose(np.abs(t), 1/(4*beta))
    regular = ~(zero|edge)
    u = t[regular]
    h[regular] = (np.sin(np.pi*u*(1-beta))+4*beta*u*np.cos(np.pi*u*(1+beta)))/(np.pi*u*(1-(4*beta*u)**2))
    h[zero] = 1+beta*(4/np.pi-1)
    h[edge] = beta/np.sqrt(2)*((1+2/np.pi)*np.sin(np.pi/(4*beta))+(1-2/np.pi)*np.cos(np.pi/(4*beta)))
    return h/np.sqrt(np.sum(h*h))


def gardner(x, sps):
    """Early/late feedback with bounded rate drift and linear interpolation."""
    # NumPy scalars are expensive inside an ARM Python feedback loop. Convert
    # once after the vectorized phase search; keep the same interpolation and
    # loop gains using native complex arithmetic.
    offsets = np.arange(0, sps, .25)
    scores = [np.mean(np.abs(x[int(o)+32:-32:max(1, int(round(sps)))])**2) for o in offsets]
    x = x.tolist()

    def interpolate(t):
        i = int(t)
        return x[i]*(1-(t-i))+x[i+1]*(t-i)

    t = 8*sps+float(offsets[int(np.argmax(scores))])
    omega, samples = float(sps), []
    while t+omega/2+1 < len(x)-8*sps:
        early, center, late = interpolate(t-omega/2), interpolate(t), interpolate(t+omega/2)
        error = max(-2., min(2., float(((late-early)*center.conjugate()).real)))
        samples.append(center)
        omega = max(.95*sps, min(1.05*sps, omega+.0002*error))
        t += omega+.02*error
    return np.asarray(samples)


def refine(iq, family, fs=AMC_FS, *, timing_recovery=None):
    if fs != AMC_FS or family not in ('PSK-high', 'QAM'):
        raise ValueError('Refinement requires PSK-high/QAM at 480 kSPS')
    x = complex_iq(iq)
    if len(x) != 1:
        raise ValueError('Refinement accepts one capture at a time')
    x = x[0].astype(np.complex128)
    x -= x.mean()
    x /= np.sqrt(np.mean(np.abs(x)**2)).clip(1e-12)
    sps, prominence = estimate_sps(x)
    # Estimate CFO after matched filtering: powering raw wideband noise to
    # order eight destroys the QPSK carrier line at modest occupied-band SNR.
    # Fourth-power correction is also applied to 8PSK; its absent coherent
    # fourth-order line is the discriminating statistic, not a supplied label.
    taps = rrc(sps)
    matched = np.convolve(x, taps, mode='same')
    corrected, frequency = correct_cfo(matched, sps, 4)
    symbols = (gardner if timing_recovery is None else timing_recovery)(corrected, sps)
    if len(symbols) < 64:
        raise ValueError('Blind synchronization produced too few symbols')
    symbols -= symbols.mean()
    symbol_power = float(np.mean(np.abs(symbols)**2))
    # AWGN estimate from unoccupied high-frequency bins. Signal bandwidth is
    # <=0.3375*fs under the documented sps range, well below this guard band.
    raw_psd = np.abs(np.fft.fft(x))**2/len(x)
    noise = float(np.median(raw_psd[np.abs(np.fft.fftfreq(len(x))) > .35])/np.log(2))
    signal_fraction = max(.1, 1-noise/symbol_power)
    symbols /= np.sqrt(symbol_power).clip(1e-12)
    m20 = np.mean(symbols**2)
    # Average magnitudes over fixed 64-symbol windows so residual carrier
    # rotation cannot cancel the fourth-order statistic across the capture.
    # The theoretical QPSK/8PSK midpoint remains .5; no fitted threshold.
    blocks = symbols[:len(symbols)//64*64].reshape(-1, 64)
    c40 = float(np.mean(np.abs(np.mean(blocks**4, axis=1)
                              -3*np.mean(blocks**2, axis=1)**2)))/signal_fraction**2
    c42 = float(np.mean(np.abs(symbols)**4)-abs(m20)**2-2)/signal_fraction**2
    if family == 'PSK-high':
        label = 'QPSK' if c40 >= .5 else '8PSK'
        margin = abs(float(c40)-.5)/.5
    else:
        # Ideal C42=-.68 (16QAM) and -.6190476 (64QAM). Matched filtering
        # reduces noise; this narrow separation remains a known limitation.
        label = '16QAM' if c42 < -.6495238 else '64QAM'
        margin = abs(c42+.6495238)/.0304762
    return dict(label=label, confidence=float(np.clip(.5+.5*margin, .5, 1)),
                sps=sps, rate_prominence=prominence, cfo_hz=frequency*fs,
                c40=float(c40), c42=c42, symbols=symbols.astype(np.complex64))
