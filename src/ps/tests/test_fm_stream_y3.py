import numpy as np
import pytest

from src.ps.sentinel.fm_stream_y3 import FmStream, pcm24_words


def modulated(count, tone_hz=1000, deviation=10000):
    t = np.arange(count)/480000
    return np.exp(2j*np.pi*np.cumsum(deviation*np.sin(2*np.pi*tone_hz*t))/480000)


def test_arbitrary_chunk_boundaries_equal_unbroken_signal():
    iq = modulated(96007)
    ref = FmStream().process(iq, 0)
    stream = FmStream()
    output = []
    rng = np.random.default_rng(134)
    offset = 0
    while offset < len(iq):
        size = int(rng.integers(1, 4097))
        output.append(stream.process(iq[offset:offset+size], offset))
        offset += min(size, len(iq)-offset)
    np.testing.assert_allclose(np.concatenate(output), ref, rtol=0, atol=1e-7)
    assert stream.output_samples == (len(iq)+9)//10
    assert stream.clipped_samples == 0


def test_20ms_pcm_chunks_match_continuous_reference():
    iq = modulated(480000)
    reference = pcm24_words(FmStream().process(iq, 0))
    stream = FmStream()
    chunks = [pcm24_words(stream.process(iq[start:start+9600], start))
              for start in range(0, len(iq), 9600)]
    np.testing.assert_array_equal(np.concatenate(chunks), reference)
    assert stream.output_samples == 48000


def test_demodulated_tone_and_75us_deemphasis():
    out = FmStream().process(modulated(480000), 0)[4800:]
    expected = .2*(10000/75000)/np.sqrt(1+(2*np.pi*1000*75e-6)**2)
    amplitude = np.sqrt(2)*np.std(out)
    assert abs(amplitude/expected-1) < .02
    spectrum = np.abs(np.fft.rfft(out*np.hanning(len(out))))
    frequency = np.argmax(spectrum)*48000/len(out)
    assert abs(frequency-1000) < 2


def test_gap_or_nonfinite_rejected_without_advancing_state():
    stream = FmStream()
    for iq, first in [(modulated(20), 1), (np.array([1+np.nan*1j]), 0), (np.zeros(2), 0)]:
        with pytest.raises(ValueError):
            stream.process(iq, first)
        assert stream.input_samples == 0


def test_i2s_signed_pcm_words_and_clamp():
    words = pcm24_words(np.array([-2, -1, -.5, 0, .5, 1, 2]))
    assert (words & 0xffffff).tolist() == [0x800000, 0x800000, 0xc00000, 0,
                                        0x400000, 0x7fffff, 0x7fffff]
