"""Offline antenna-capture FM diagnostic; no classifier or RF station labels."""
import numpy as np
from scipy.signal import bilinear, butter, firwin, lfilter, resample_poly, sosfilt, welch


def demodulate_chunk(iq, sample_rate_hz, lo_hz, candidate_hz, profile='wide'):
    if profile not in ('wide','voice'):
        raise ValueError('Unknown audio diagnostic profile')
    iq = np.asarray(iq, dtype=np.complex128)
    factor = int(round(sample_rate_hz/480000))
    if iq.ndim != 1 or len(iq) < sample_rate_hz*.05 or factor < 1 or abs(factor*480000-sample_rate_hz) > 2:
        raise ValueError('Need >50ms complex IQ with an integer decimation to480kHz')
    n = np.arange(len(iq))
    shifted = iq*np.exp(2j*np.pi*(lo_hz-candidate_hz)*n/sample_rate_hz)
    baseband = resample_poly(shifted, 1, factor)
    baseband = lfilter(firwin(129,120000,fs=480000),1,baseband)
    frequency = np.angle(baseband[1:]*baseband[:-1].conj())*(480000/(2*np.pi))
    frequency = frequency[9600:-480]  # discard20ms startup and1ms ending edge
    corrected_fraction=0.
    if profile=='voice':
        strength=np.minimum(abs(baseband[1:]),abs(baseband[:-1]))[9600:-480]
        center=np.median(frequency)
        bad=(abs(frequency-center)>150000)|((strength<.1*np.median(strength))&(abs(frequency-center)>100000))
        # Only bridge very short phase slips; do not invent audio over fades.
        edges=np.diff(np.r_[False,bad,False].astype(np.int8))
        eligible=np.zeros(len(bad),dtype=bool)
        for start,stop in zip(np.flatnonzero(edges==1),np.flatnonzero(edges==-1)):
            if stop-start<=8:eligible[start:stop]=True
        if eligible.mean()<=.02 and np.any(eligible):
            good=np.flatnonzero(~eligible)
            frequency[eligible]=np.interp(np.flatnonzero(eligible),good,frequency[good])
            corrected_fraction=float(eligible.mean())
    offset = float(np.mean(frequency))
    frequency -= offset
    f, p = welch(frequency,fs=480000,nperseg=min(16384,len(frequency)))
    pilot_band=(f>=18800)&(f<=19200)
    nearby=((f>=18000)&(f<=20000))&~((f>=18700)&(f<=19300))
    indices=np.flatnonzero(pilot_band)
    peak=indices[int(np.argmax(p[pilot_band]))]
    prominence=float(10*np.log10(max(p[peak],1e-30)/max(np.median(p[nearby]),1e-30)))
    result=dict(pilot_frequency_hz=float(f[peak]),pilot_prominence_db=prominence,
                stereo_pilot_evidence=bool(abs(f[peak]-19000)<80 and prominence>=12),
                discriminator_mean_offset_hz=offset,
                demod_frequency_rms_hz=float(np.std(frequency)),
                audio_sample_rate_hz=48000,audio_profile=profile,
                short_phase_slip_corrected_fraction=corrected_fraction)
    b,a=bilinear([1],[50e-6,1],fs=480000)
    audio=lfilter(b,a,frequency)
    if profile=='voice':
        audio=sosfilt(butter(6,3400,fs=480000,output='sos'),audio)
        audio=sosfilt(butter(4,150,'highpass',fs=480000,output='sos'),audio)
    else:
        audio=sosfilt(butter(4,15000,fs=480000,output='sos'),audio)
        audio=sosfilt(butter(2,50,'highpass',fs=480000,output='sos'),audio)
    audio=resample_poly(audio,1,10)
    fade=min(240,len(audio)//2)
    if fade:
        ramp=np.linspace(0,1,fade)
        audio[:fade]*=ramp;audio[-fade:]*=ramp[::-1]
    return audio,result,f,p
