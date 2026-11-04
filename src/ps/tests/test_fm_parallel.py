"""DSP continuity, channel selection, alias rejection and wire sample indices."""
import numpy as np
import pytest

from src.ps.sentinel.fm_parallel import ParallelFM, audio_chunks


def fm_iq(count, offset=-250000):
    time = np.arange(count)/3840000
    return np.exp(1j*(2*np.pi*offset*time+20*np.sin(2*np.pi*1000*time)))


def test_arbitrary_dma_boundaries_equal_one_continuous_capture():
    iq = fm_iq(384001)
    reference = ParallelFM(95800000, 96050000).process(iq, 0)
    stream = ParallelFM(95800000, 96050000)
    result = []
    index = 0
    for count in (1, 2, 4, 37, 1000, 65536, 79, 131072, 186270):
        part = iq[index:index+count]
        result.append(stream.process(part, index))
        index += len(part)
    if index < len(iq):
        result.append(stream.process(iq[index:], index))
    np.testing.assert_allclose(np.concatenate(result), reference, atol=1)
    assert len(reference) == 4801
    audio = reference[1000:].astype(float)
    frequency = np.fft.rfftfreq(len(audio), 1/48000)
    assert abs(frequency[np.argmax(abs(np.fft.rfft(audio))) ]-1000) < 20


def test_channel_filter_rejects_decimation_alias():
    stream = ParallelFM(96050000, 96050000)
    n = np.arange(129)
    passband = abs(np.sum(stream.taps*np.exp(-2j*np.pi*80000/3840000*n)))
    stopband = abs(np.sum(stream.taps*np.exp(-2j*np.pi*360000/3840000*n)))
    assert passband > .95
    assert 20*np.log10(stopband/passband) < -50


def test_rx1_lane_mapping_and_gap_rejection():
    iq = fm_iq(8000)*1000
    lanes = np.zeros((len(iq),4),dtype='<i2')
    lanes[:,0] = np.rint(iq.real)
    lanes[:,1] = np.rint(iq.imag)
    lanes[:,2:] = 30000
    a = ParallelFM(95800000,96050000)
    b = ParallelFM(95800000,96050000)
    expected = b.process(lanes[:,0].astype(float)+1j*lanes[:,1],0)
    np.testing.assert_array_equal(a.process_dma(lanes.view('u1'),0),expected)
    with pytest.raises(ValueError,match='Discontinuous'):
        a.process(iq,8001)


def test_pcm_packet_boundaries_and_sources():
    pcm = np.arange(2000,dtype='<i2')
    packets = list(audio_chunks(pcm,400))
    assert [h['first_sample_index'] for h,_ in packets] == [400,1360,2320]
    assert b''.join(p for _,p in packets) == pcm.tobytes()
    assert all(h['source']=='ps_parallel_demod' and not h['adc_sequence_certified']
               for h,_ in packets)
