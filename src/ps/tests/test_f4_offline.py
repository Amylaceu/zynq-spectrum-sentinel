"""F4 independent numerical/storage checks; all inputs synthetic, no hardware."""
import hashlib
import json

import numpy as np
import pytest

from src.ps.sentinel.panorama import (
    GROUPS, SAMPLE_RATE_HZ, dbfs_per_hz, stitch, tile_centers, welch_psd,
)
from src.ps.sentinel.stability import EvidenceStream, StabilityStats, resident_bytes


def test_psd_frequency_sign_and_complex_full_scale_power():
    nfft = 4096
    frequency = -333 * SAMPLE_RATE_HZ / nfft
    t = np.arange(3 * nfft) / SAMPLE_RATE_HZ
    iq = 1024 * np.exp(2j * np.pi * frequency * t)
    axis, power = welch_psd(iq, nfft=nfft)
    assert axis[np.argmax(power)] == pytest.approx(frequency)
    # Half-scale complex sinusoid: integrated PSD = 0.5^2, not half of that.
    assert np.sum(power) * SAMPLE_RATE_HZ / nfft == pytest.approx(0.25, rel=1e-9)


def test_random_iq_parseval_uses_window_energy_and_does_not_remove_dc():
    rng = np.random.default_rng(84)
    nfft = 1024
    iq = 75 + rng.normal(0, 10, nfft) + 1j * rng.normal(0, 10, nfft)
    _, power = welch_psd(iq, nfft=nfft)
    window = np.hanning(nfft)
    expected = np.sum(abs(iq / 2048 * window) ** 2) / np.sum(window ** 2)
    assert power.sum() * SAMPLE_RATE_HZ / nfft == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize('group', ['A', 'D'])
def test_plan_covers_both_endpoints_and_dc_gaps(group):
    axis = np.fft.fftshift(np.fft.fftfreq(4096, 1 / SAMPLE_RATE_HZ))
    tiles = ((lo, axis, np.ones(len(axis))) for lo in tile_centers(group))
    frequency, power, count = stitch(tiles, group)
    assert frequency[0] == GROUPS[group][0] + 5000
    assert frequency[-1] == GROUPS[group][1] - 5000
    assert np.all(count > 0)
    assert np.all(power == 1)


def test_single_tile_does_not_fabricate_coverage_at_dc_or_outside_passband():
    axis = np.linspace(-15000000, 15000000, 4096)
    frequency, power, count = stitch([(100000000, axis, np.ones(len(axis)))], 'A')
    dc = abs(frequency - 100000000) < 150000
    edge = abs(frequency - 100000000) > 10000000
    assert np.all(count[dc | edge] == 0)
    assert np.all(np.isnan(power[dc | edge]))
    assert np.all(np.isnan(dbfs_per_hz(power)[dc | edge]))


def test_overlaps_average_linear_power_not_decibels():
    axis = np.linspace(-15000000, 15000000, 4096)
    frequency, power, count = stitch([
        (100000000, axis, np.ones(len(axis))),
        (100000000, axis, np.full(len(axis), 0.01)),
    ], 'A')
    index = int(np.argmin(abs(frequency - 103000000)))
    assert count[index] == 2
    assert power[index] == pytest.approx(0.505)
    assert dbfs_per_hz(power)[index] == pytest.approx(-2.9670862188)


@pytest.mark.parametrize('change', ['real', 'nonfinite', 'short'])
def test_bad_capture_rejected(change):
    iq = np.ones(8192, dtype=complex)
    if change == 'real':
        iq = iq.real
    elif change == 'nonfinite':
        iq[0] = complex(float('nan'), 0)
    else:
        iq = iq[:100]
    with pytest.raises(ValueError):
        welch_psd(iq)


def test_stream_bounded_without_losing_file_records_and_digest(tmp_path):
    path = tmp_path / 'telemetry.jsonl'
    sink = EvidenceStream(path, recent_limit=3)
    record = {'index': 0}
    for index in range(1000):
        record['index'] = index
        sink.append(record)
    record['index'] = -1
    assert sink.count == 1000
    assert [r['index'] for r in sink.recent] == [997, 998, 999]
    result = sink.close()
    assert result == sink.close()
    lines = path.read_text().splitlines()
    assert len(lines) == 1000 and json.loads(lines[-1])['index'] == 999
    assert result['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert path.with_suffix('.jsonl.sha256').read_text().split()[0] == result['sha256']
    with pytest.raises(ValueError):
        sink.append({})
    with pytest.raises(FileExistsError):
        EvidenceStream(path)


def test_stream_refuses_nan_before_writing_partial_json(tmp_path):
    sink = EvidenceStream(tmp_path / 'events.jsonl')
    with pytest.raises(ValueError):
        sink.append({'bad': float('nan')})
    assert sink.count == 0
    sink.close()
    assert sink.path.read_bytes() == b''


def sample(second, **overrides):
    value = dict(elapsed_s=second, rss_bytes=50000000, temperature_c=60.0,
                 display_fps=40.0, processing_status=0)
    value.update(overrides)
    return value


def synthetic_hour(change=None):
    stats = StabilityStats()
    for second in range(3601):
        stats.observe(sample(second, **((change or {}) if second == 100 else {})))
    return stats


def test_synthetic_hour_meets_criteria_but_short_or_interrupted_run_never_passes():
    stats = synthetic_hour()
    assert stats.finish(3600, True, 1500, 2)['status'] == 'PASS'
    assert stats.finish(3600, False, 1500, 2)['status'] == 'FAIL'
    assert stats.finish(3600, True, 0, 2)['status'] == 'FAIL'
    short = StabilityStats()
    short.observe(sample(0))
    short.observe(sample(10))
    assert short.finish(10, True, 4, 0)['status'] == 'FAIL'
    # Merely changing the reported duration cannot turn a short trace into an hour.
    assert short.finish(3600, True, 4, 0)['status'] == 'FAIL'


@pytest.mark.parametrize('change,failed', [
    ({'rss_bytes': 60000000}, 'memory_growth_under_10MB'),
    ({'temperature_c': 85.0}, 'temperature_below_85C'),
    ({'processing_status': 1}, 'zero_processing_faults'),
])
def test_transient_fault_or_exact_limit_is_not_hidden_by_normal_final_sample(change, failed):
    summary = synthetic_hour(change).finish(3600, True, 10, 0)
    assert summary['status'] == 'FAIL'
    assert summary['checks'][failed] is False


def test_telemetry_gap_or_invalid_sample_prevents_acceptance():
    stats = StabilityStats()
    stats.observe(sample(0))
    with pytest.raises(ValueError):
        stats.observe(sample(1, temperature_c=None))
    with pytest.raises(ValueError):
        stats.observe(sample(0))
    stats.observe(sample(3600))
    result = stats.finish(3600, True, 10, 0)
    assert not result['checks']['valid_telemetry']
    assert not result['checks']['telemetry_coverage']


def test_current_rss_reading_uses_linux_units_and_rejects_missing(tmp_path):
    path = tmp_path / 'status'
    path.write_text('Name:\tpython\nVmHWM:\t20000 kB\nVmRSS:\t12345 kB\n')
    assert resident_bytes(path) == 12345 * 1024
    path.write_text('Name:\tpython\n')
    with pytest.raises(ValueError):
        resident_bytes(path)
