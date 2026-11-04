import numpy as np
from src.ps.sentinel.fm_receive import demodulate_chunk


def test_fm_pilot_and_audio_with_offset_tuning():
    fs=3840000;n=np.arange(384000);t=n/fs
    modulation=75000*(.5*np.sin(2*np.pi*1000*t)+.1*np.sin(2*np.pi*19000*t))
    z=np.exp(2j*np.pi*np.cumsum(modulation)/fs)*np.exp(-2j*np.pi*250000*t)
    audio,result,_,_=demodulate_chunk(z,fs,90250000,90000000)
    assert result['stereo_pilot_evidence']
    assert abs(result['pilot_frequency_hz']-19000)<80
    freq=np.fft.rfftfreq(len(audio),1/48000)
    assert abs(freq[np.argmax(abs(np.fft.rfft(audio)))]-1000)<30


def test_noise_does_not_pass_pilot_evidence():
    rng=np.random.default_rng(12)
    z=rng.normal(size=384000)+1j*rng.normal(size=384000)
    _,result,_,_=demodulate_chunk(z,3840000,90250000,90000000)
    assert not result['stereo_pilot_evidence']


def test_voice_profile_retains_speech_tone_and_rejects_high_frequency_noise():
    fs=3840000;t=np.arange(768000)/fs
    modulation=30000*np.sin(2*np.pi*1000*t)+5000*np.sin(2*np.pi*8000*t)
    z=np.exp(2j*np.pi*np.cumsum(modulation)/fs)*np.exp(-2j*np.pi*250000*t)
    wide,*_=demodulate_chunk(z,fs,90250000,90000000)
    voice,result,*_=demodulate_chunk(z,fs,90250000,90000000,profile='voice')
    def amplitude(audio,hz):
        audio=audio[1000:-1000]
        return abs(np.mean(audio*np.exp(-2j*np.pi*hz*np.arange(len(audio))/48000)))
    assert amplitude(voice,1000)>.8*amplitude(wide,1000)
    assert amplitude(voice,8000)<.02*amplitude(wide,8000)
    assert result['short_phase_slip_corrected_fraction']<.001
