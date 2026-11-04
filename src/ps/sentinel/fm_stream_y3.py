"""Stateful NumPy-only Y3 fallback: contiguous480k IQ to mono48k PCM.

This does not make gapped Y2 SCAP snapshots continuous. The capture layer must
check FIFO/sequence continuity and supply the true first_sample_index. No RF or
audio device is opened here. Rates are nominal until actual clocks are audited.
"""
import math

import numpy as np


class FmStream:
    input_rate = 480000
    output_rate = 48000
    decimation = 10

    def __init__(self, deviation_hz=75000.0, gain=.2):
        if not math.isfinite(deviation_hz) or deviation_hz <= 0:
            raise ValueError('Positive finite deviation required')
        if not math.isfinite(gain) or not 0 < gain <= 1:
            raise ValueError('Gain must be in (0,1]')
        self.deviation_hz, self.gain = deviation_hz, gain
        # Anti-alias filter precedes decimation; no independent per-block reset.
        index = np.arange(161, dtype=np.float64)-80
        cutoff = 17000/self.input_rate
        taps = 2*cutoff*np.sinc(2*cutoff*index)*np.hamming(161)
        self.lowpass = taps/taps.sum()
        alpha = math.exp(-1/(self.output_rate*75e-6))
        self.deemphasis = (1-alpha)*alpha**np.arange(64, dtype=np.float64)
        self.history = np.zeros(160, dtype=np.float64)
        self.audio_history = np.zeros(63, dtype=np.float64)
        self.previous_iq = 1+0j
        self.input_samples = self.output_samples = self.clipped_samples = 0

    def process(self, iq, first_sample_index):
        if type(first_sample_index) is not int or first_sample_index != self.input_samples:
            raise ValueError('Discontinuous IQ: stop/re-prime the stream explicitly')
        iq = np.asarray(iq)
        if iq.ndim != 1 or not np.iscomplexobj(iq) or not np.all(np.isfinite(iq)):
            raise ValueError('Require finite one-dimensional complex IQ')
        if not len(iq):
            return np.zeros(0, dtype=np.float32)
        previous = np.concatenate(([self.previous_iq], iq[:-1]))
        phase = np.angle(iq*previous.conj())
        frequency = phase*(self.input_rate/(2*np.pi*self.deviation_hz))
        stream = np.concatenate((self.history, frequency))
        first = (-self.input_samples) % self.decimation
        count = max(0, (len(iq)-1-first)//self.decimation+1)
        if count:
            # Bounds: last window ends <= len(history)+len(iq), including tiny
            # arbitrary chunks. Only selected decimation phases are evaluated.
            windows = np.lib.stride_tricks.as_strided(stream[first:],
                shape=(count, len(self.lowpass)),
                strides=(stream.strides[0]*self.decimation, stream.strides[0]),
                writeable=False)
            decimated = np.einsum('ij,j->i', windows, self.lowpass[::-1])
            joined = np.concatenate((self.audio_history, decimated))
            audio = np.convolve(joined, self.deemphasis, mode='valid')*self.gain
            self.audio_history = joined[-63:].copy()
        else:
            audio = np.zeros(0, dtype=np.float64)
        self.history = stream[-160:].copy()
        self.previous_iq = complex(iq[-1])
        self.input_samples += len(iq)
        self.output_samples += len(audio)
        self.clipped_samples += int(np.count_nonzero(np.abs(audio) > .95))
        return np.clip(audio, -.95, .95).astype(np.float32)


def pcm24_words(audio):
    """Signed24-bit sample in low24 bits; high8 bits are sign-extension."""
    audio = np.asarray(audio)
    if audio.ndim != 1 or not np.all(np.isfinite(audio)):
        raise ValueError('Require finite mono audio')
    return np.clip(np.rint(audio*8388608), -8388608, 8388607).astype('<i4').view('<u4')
