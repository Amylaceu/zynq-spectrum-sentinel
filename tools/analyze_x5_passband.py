"""Characterize the frozen PFB prototype; no RF, RTL changes or model fitting.

This floating FIR calculation explains frequency-dependent channel coverage.
It is not a replacement for bit-accurate simulation or a measured RF response.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy.signal import freqz, lfilter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src/ps'))
from sentinel.capture_x5 import select_channel


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = ROOT/'board/measurements/x5_prototype_response.json'
    figure = ROOT/'report/figures/x5_prototype_response.png'
    if output.exists() or figure.exists():
        raise FileExistsError('Preserve existing characterization')
    coefficients = ROOT/'src/rtl/pfb/x5_pfb_coeff.hex'
    words = np.array([int(line, 16) for line in coefficients.read_text().split()])
    if words.shape != (128,) or np.any(words < 0) or np.any(words >= 2**18):
        raise ValueError('Expected 128 signed Q1.17 prototype coefficients')
    taps = np.where(words >= 2**17, words-2**18, words)/2**17
    rate = 3840000
    frequencies = np.arange(0, 240001, 250)
    _, response = freqz(taps, worN=frequencies, fs=rate)
    dc = abs(response[0])
    gains = 20*np.log10(np.maximum(abs(response)/dc, 1e-15))
    # An independent sinusoidal convolution verifies selected frequency samples.
    checks = []
    for frequency in (0, 40000, 80000, 120000, 160000, 200000, 240000):
        tone = np.exp(2j*np.pi*frequency*np.arange(2048)/rate)
        measured = np.mean(abs(lfilter(taps, [1], tone)[256:]))/dc
        analytic = abs(freqz(taps, worN=[frequency], fs=rate)[1][0])/dc
        if abs(measured-analytic) > 1e-12:
            raise ValueError('Sinusoidal FIR cross-check differs')
        checks.append(dict(offset_hz=frequency, gain_db=float(20*np.log10(analytic)),
                           absolute_gain_error=float(abs(measured-analytic))))
    stations = []
    for frequency, truth in ((95800000, 'USER_CONFIRMED_FM'),
                             (95451250, 'HIGH_DETECTION_ONLY_IDENTITY_UNCONFIRMED')):
        selection = select_channel(frequency-96400000)
        offsets = selection.residual_hz+np.array([-75000, 0, 75000])
        amplitude = abs(freqz(taps, worN=offsets, fs=rate)[1])/dc
        stations.append(dict(frequency_hz=frequency, truth=truth,
                             channel=selection.channel, residual_hz=selection.residual_hz,
                             illustrative_offsets_from_channel_center_hz=offsets.tolist(),
                             illustrative_gain_db=(20*np.log10(amplitude)).tolist(),
                             bandwidth_assumption='Illustrative +/-75kHz, not measured station bandwidth'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4.5), layout='constrained')
    ax.plot(frequencies/1000, gains, label='Frozen 128-tap Q1.17 prototype')
    ax.axvline(120, color='tab:red', linestyle='--', label='Half channel spacing: 120 kHz')
    ax.axhline(-3, color='gray', linestyle=':', linewidth=1)
    ax.axhline(-6, color='gray', linestyle=':', linewidth=1)
    ax.set(xlabel='Absolute offset from PFB channel center (kHz)',
           ylabel='Gain relative to DC (dB)', ylim=(-100, 2), xlim=(0, 240),
           title='480 kSPS output rate does not imply a flat 480 kHz channel')
    ax.grid(alpha=.25)
    ax.legend(loc='lower left')
    fig.savefig(figure, dpi=160)
    plt.close(fig)
    value = dict(status='CHARACTERIZED', recorded_at_pc=datetime.now(timezone.utc).isoformat(),
                 scope='Ideal floating FIR response only; not an RF/AMC acceptance or a new core simulation round',
                 input_rate_hz=rate, output_rate_hz=480000, channel_spacing_hz=240000,
                 maximum_grid_offset_above_minus3db_hz=int(frequencies[gains >= -3][-1]),
                 sinusoidal_cross_checks=checks, illustrative_station_placement=stations,
                 limitations=['No ADC/RF analog response, fixed-point FFT or noise model included',
                              'Post-PFB NCO cannot recover a sideband already suppressed by the prototype',
                              'This does not prove the cause of X1 detection failures'],
                 source_sha256={p.relative_to(ROOT).as_posix(): sha(p) for p in
                                (Path(__file__), coefficients, ROOT/'src/ps/sentinel/capture_x5.py')},
                 figure=figure.relative_to(ROOT).as_posix(), figure_sha256=sha(figure))
    output.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
    for path in (output, figure):
        Path(str(path)+'.sha256').write_text(sha(path)+'  '+path.name+'\n', encoding='ascii')
    print(json.dumps(value, indent=2))


if __name__ == '__main__':
    main()
