"""Conservative stereo-FM listening gate, not a general modulation classifier.

Intended for the independently confirmed 95.8 MHz stereo station. A missing
pilot cannot reject mono FM as a modulation class. Metrics are not calibrated
SNR, and a silent gate is never successful audio reception.
"""
import numpy as np


def stereo_quality(iq, sample_rate_hz=480000):
    iq = np.asarray(iq, dtype=np.complex128)
    if iq.ndim != 1 or len(iq) < 4096 or sample_rate_hz != 480000:
        raise ValueError('Require at least 4096 IQ at 480 kSPS')
    if not np.all(np.isfinite(iq)):
        raise ValueError('IQ must be finite')
    frequency = np.angle(iq[1:]*iq[:-1].conj())*sample_rate_hz/(2*np.pi)
    steady = frequency[256:-256]
    steady = steady-np.median(steady)
    spectrum = abs(np.fft.rfft((steady-steady.mean())*np.hanning(len(steady))))**2
    bins = np.fft.rfftfreq(len(steady), 1/sample_rate_hz)
    pilot = (bins >= 18500) & (bins <= 19500)
    nearby = ((bins >= 17000) & (bins <= 21000)) & ~pilot
    peak = np.flatnonzero(pilot)[np.argmax(spectrum[pilot])]
    prominence = float(10*np.log10(max(spectrum[peak], 1e-30)/max(np.median(spectrum[nearby]), 1e-30)))
    slips = float(np.mean(abs(steady) > 150000))
    rms = float(np.sqrt(np.mean(abs(iq)**2)))
    frequency_hz = float(bins[peak])
    good = (abs(frequency_hz-19000) <= 100 and prominence >= 14
            and slips <= .01 and 1e-4 < rms < .9)
    return dict(good=bool(good), pilot_frequency_hz=frequency_hz,
                pilot_prominence_db=prominence, large_excursion_fraction=slips,
                iq_rms=rms, scope='Stereo pilot/phase integrity; not SNR or station identity')


class StereoQualityGate:
    """Require three good snapshots to open; close on two bad snapshots."""
    def __init__(self):
        self.open = False
        self.good_count = 0
        self.bad_count = 0

    def update(self, metrics):
        if metrics['good']:
            self.good_count += 1
            self.bad_count = 0
            if self.good_count >= 3:
                self.open = True
        else:
            self.good_count = 0
            self.bad_count += 1
            if self.bad_count >= 2:
                self.open = False
        return self.open
