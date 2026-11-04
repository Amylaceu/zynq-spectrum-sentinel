import numpy as np
import pytest

from sim.golden.cfar import cluster
from sim.golden.demod import am_demod, fm_demod, resample_to_48k
from sim.golden.render import PALETTE, render_frame


def test_fm_phase_wrap_and_audio_message():
    fs, fm, deviation = 192000, 1000, 12000
    t = np.arange(19200) / fs
    message = np.cos(2 * np.pi * fm * t)
    phase = 2 * np.pi * deviation / fs * np.cumsum(message)
    output = fm_demod(np.exp(1j * phase))
    reference = 2 * np.pi * deviation / fs * message
    sqnr = 10 * np.log10(np.sum(reference[1:]**2) / np.sum((output[1:] - reference[1:])**2))
    print(f"phase16 FM SQNR={sqnr:.2f} dB")
    assert sqnr > 60 and output[0] == 0


def test_am_message_after_dc_startup():
    fs = 192000
    t = np.arange(192000) / fs
    message = 0.5 * np.cos(2 * np.pi * 1000 * t)
    output = am_demod((1 + message) * np.exp(2j * np.pi * 14000 * t))
    assert np.corrcoef(output[15000:], message[15000:])[0, 1] > 0.999
    assert abs(np.std(output[15000:]) / np.std(message[15000:]) - 1) < 0.005


def test_resampling_audio_rate_frequency_and_stopband():
    fs = 192000
    n = np.arange(fs)
    output = resample_to_48k(np.cos(2 * np.pi * 1000 * n / fs), fs)
    assert len(output) == 48000
    assert np.argmax(np.abs(np.fft.rfft(output))) == 1000
    blocked = resample_to_48k(np.cos(2 * np.pi * 50000 * n / fs), fs)[100:-100]
    assert 10 * np.log10(np.mean(blocked**2)) < -65


def frame(**kwargs):
    args = dict(spec_db_q88=None, peak_db_q88=None, thr_db_q88=None, targets=None,
                wf_rows=None, dpx_hist=None, ui_rgb565=None)
    args.update(kwargs)
    return render_frame(**args)


def test_actual_display_dimensions_and_palette_endpoints():
    f = frame()
    assert f.shape == (480, 800) and f.dtype == np.uint16 and not f.any()
    assert PALETTE.shape == (256,) and PALETTE[0] == 0 and PALETTE[255] == 0xF800


def test_continuous_trace_and_dashed_threshold_pixels():
    trace = np.full(720, -100 * 256, dtype=np.int16)
    trace[1] = 0
    f = frame(spec_db_q88=trace)
    assert np.all(f[:160, 1] == 0x07FF) and np.all(f[:160, 2] == 0x07FF)
    threshold = frame(thr_db_q88=np.full(720, -50 * 256))
    assert np.all(threshold[79, :8] == [0xF800, 0xF800, 0, 0, 0xF800, 0xF800, 0, 0])


def test_waterfall_ring_and_density_mapping():
    wf = np.zeros((200, 720), dtype=np.uint8)
    wf[:, :] = np.arange(200, dtype=np.uint8)[:, None]
    density = np.full((128, 360), 100, dtype=np.uint8)
    f = frame(wf_rows=wf, dpx_hist=density, cfg={"wf_head": 198})
    assert np.all(f[:160, :720] == PALETTE[100])
    assert f[160, 0] == PALETTE[198] and f[162, 0] == PALETTE[0]
    assert np.all(f[360:] == 0) and np.all(f[:, 720:] == 0)


def test_target_box_and_ui_transparency_priority():
    hit = np.zeros(2048, dtype=np.uint8)
    hit[100:111] = 1
    targets = cluster(hit, hit.astype(np.uint32))
    ui = np.full((480, 800), 0xF81F, dtype=np.uint16)
    ui[0, 35] = 0xFFFF
    f = frame(targets=targets, ui_rgb565=ui)
    assert f[1, 35] == 0x07E0 and f[0, 35] == 0xFFFF
    assert f[0, 37] == 0x07E0


def test_pixel_bin_peak_reduction():
    s = np.full(2048, -100 * 256)
    s[200] = 0
    f = frame(spec_db_q88=s)
    x = next(j for j in range(720) if j * 2048 // 720 <= 200 < (j + 1) * 2048 // 720)
    assert f[0, x] == 0x07FF


def test_invalid_inputs_and_empty_audio():
    assert len(fm_demod([])) == len(am_demod([])) == 0
    with pytest.raises(ValueError):
        frame(ui_rgb565=np.zeros((600, 1024), dtype=np.uint16))
    with pytest.raises(ValueError):
        frame(dpx_hist=np.zeros((160, 720), dtype=np.uint8))
