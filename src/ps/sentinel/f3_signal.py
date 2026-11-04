"""Deterministic F3 calibration waveform and explicitly band-limited metrics."""
import numpy as np


def cw_words(n=16384, bin_index=1024, peak=512):
    if type(n) is not int or n < 2048 or n % 16 or not 1 <= peak <= 1023:
        raise ValueError('Invalid native12 waveform')
    tone = peak*np.exp(2j*np.pi*bin_index*np.arange(n)/n)
    words = np.zeros((n, 4), dtype='<i2')
    words[:, 0] = np.rint(tone.real).astype('<i2')*16
    words[:, 1] = np.rint(tone.imag).astype('<i2')*16
    return words


def tone_metrics(iq, fs=3840000, expected=240000):
    """Windowed CW power in +/-2 bins / remaining +/-750kHz band power.

    This is a CW diagnostic SINAD-like ratio, not modulation occupied-band SNR.
    Excludes the DC +/-2-bin guard from both signal and residual estimates.
    """
    x = np.asarray(iq)
    if x.ndim != 1 or len(x) < 2048 or not np.isfinite(x).all():
        raise ValueError('Invalid IQ')
    f = np.fft.fftfreq(len(x), 1/fs)
    power = np.abs(np.fft.fft((x-np.mean(x))*np.hanning(len(x))))**2
    allowed = np.abs(f-expected) <= 2000
    peak = int(np.flatnonzero(allowed)[np.argmax(power[allowed])])
    sigmask = np.abs(f-f[peak]) <= 2.01*fs/len(x)
    band = (np.abs(f) < 750000) & (np.abs(f) > 2.01*fs/len(x))
    s = float(power[sigmask].sum())
    n = float(power[band & ~sigmask].sum())
    db = float(10*np.log10(max(s, 1e-30)/max(n, 1e-30)))
    return dict(cw_ratio_db=db, peak_hz=float(f[peak]), residual_band_hz=1500000,
                rms_native=float(np.sqrt(np.mean(np.abs(x)**2))),
                max_component=float(max(np.max(np.abs(x.real)), np.max(np.abs(x.imag)))),
                metric='CW power +/-2 bins / residual in +/-750kHz, excluding DC +/-2bins')
