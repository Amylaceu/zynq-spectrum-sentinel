"""Stateful receive-only 3.84 MSPS RX1 channel to 48 kHz mono PCM.

No hardware is opened here. Input indices describe delivered DMA samples,
not an absolute ADC counter. The owner must reject FIFO overflow separately.
The result is independent PS demodulation, never PL playback readback.
"""
import math

import numpy as np

from .fm_stream_y3 import FmStream


class ParallelFM:
    input_rate = 3840000
    channel_rate = 480000
    output_rate = 48000
    factor = 8

    def __init__(self, station_hz, lo_hz, gain=.4):
        offset = float(station_hz)-float(lo_hz)
        if not math.isfinite(offset) or abs(offset) > self.input_rate/2-240000:
            raise ValueError('FM channel must fit inside received Nyquist band')
        self.offset = offset
        index = np.arange(129, dtype=float)-64
        cutoff = 120000/self.input_rate
        taps = 2*cutoff*np.sinc(2*cutoff*index)*np.hamming(129)
        self.taps = taps/taps.sum()
        self.history = np.zeros(128, dtype=np.complex128)
        self.input_samples = self.channel_samples = 0
        self.fm = FmStream(gain=gain)

    def process(self, iq, first_sample_index):
        if type(first_sample_index) is not int or first_sample_index != self.input_samples:
            raise ValueError('Discontinuous raw IQ; no hidden gap repair')
        iq = np.asarray(iq)
        if iq.ndim != 1 or not np.iscomplexobj(iq) or not np.all(np.isfinite(iq)):
            raise ValueError('Require finite complex RX1 IQ')
        if not len(iq):
            return np.zeros(0, dtype='<i2')
        # Keep the initial phase bounded across arbitrarily long captures.
        phase0 = (self.input_samples*self.offset/self.input_rate) % 1
        phase = -2*np.pi*(phase0+self.offset/self.input_rate*np.arange(len(iq)))
        shifted = iq*np.exp(1j*phase)
        joined = np.concatenate((self.history, shifted))
        first = (-self.input_samples) % self.factor
        count = max(0, (len(iq)-1-first)//self.factor+1)
        if count:
            windows = np.lib.stride_tricks.as_strided(joined[first:],
                shape=(count, len(self.taps)),
                strides=(joined.strides[0]*self.factor, joined.strides[0]), writeable=False)
            channel = np.einsum('ij,j->i', windows, self.taps[::-1])
        else:
            channel = np.empty(0, dtype=complex)
        self.history = joined[-128:].copy()
        self.input_samples += len(iq)
        audio = self.fm.process(channel, self.channel_samples)
        self.channel_samples += len(channel)
        return np.rint(audio*32767).astype('<i2')

    def process_dma(self, buffer, first_sample_index):
        """Frozen cpack layout: RX1 I,Q then RX2 I,Q, four signed16 words."""
        raw = np.asarray(buffer)
        if not raw.flags.c_contiguous or raw.nbytes % 8:
            raise ValueError('Require complete aligned four-word ADC frames')
        lanes = raw.view('<i2').reshape(-1, 4)
        iq = lanes[:, 0].astype(np.float64)+1j*lanes[:, 1].astype(np.float64)
        return self.process(iq, first_sample_index)


def audio_chunks(pcm, first_sample_index, chunk_samples=960):
    """Bounded PCM publications; sample offsets expose network packet loss."""
    pcm = np.asarray(pcm)
    if pcm.ndim != 1 or pcm.dtype != np.dtype('<i2'):
        raise ValueError('Require mono little-endian signed16 PCM')
    if type(first_sample_index) is not int or first_sample_index < 0:
        raise ValueError('Require a nonnegative PCM sample index')
    if type(chunk_samples) is not int or not 1 <= chunk_samples <= 24000:
        raise ValueError('PCM packet exceeds publication budget')
    for start in range(0, len(pcm), chunk_samples):
        block = pcm[start:start+chunk_samples]
        yield dict(source='ps_parallel_demod', sample_rate_hz=48000, channels=1,
                   format='s16le', first_sample_index=first_sample_index+start,
                   samples=len(block), adc_sequence_certified=False), block.tobytes()
