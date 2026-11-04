"""Synthetic F4 panorama and evidence check; never accesses SD, SSH or RF.

Run with the repository Python and a NEW output directory. The generated
plots are software validation examples, never measured RF results.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/ps'))
from sentinel.artifacts import atomic_write
from sentinel.panorama import (
    GROUPS, SAMPLE_RATE_HZ, dbfs_per_hz, stitch, tile_centers, welch_psd,
)
from sentinel.stability import EvidenceStream, StabilityStats


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sidecar(path):
    Path(str(path) + '.sha256').write_text(digest(path) + '  ' + path.name + '\n', encoding='ascii')


def synthetic_tiles(group):
    tones = {'A': (95800000, 150000000, 433920000),
             'D': (868000000, 1800000000, 2450000000)}[group]
    times = np.arange(16384) / SAMPLE_RATE_HZ
    rng = np.random.default_rng(20261104)
    for lo in tile_centers(group):
        iq = rng.normal(0, 0.1, len(times)) + 1j * rng.normal(0, 0.1, len(times))
        for frequency in tones:
            if abs(frequency - lo) < SAMPLE_RATE_HZ / 2:
                iq += 512 * np.exp(2j * np.pi * (frequency - lo) * times)
        axis, psd = welch_psd(iq)
        yield lo, axis, psd


def run(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    result = dict(status='STARTED', scope='SYNTHETIC_SOFTWARE_ONLY',
                  board_accessed=False, sd_accessed=False, hardware_test_pass=False,
                  notes=['No measured RF panorama or one-hour stability claim.',
                         'Separate antenna groups; uncalibrated relative ADC full-scale units.'],
                  groups={})
    result_path = output / 'result.json'
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        figure, plots = plt.subplots(2, 1, figsize=(11, 6), constrained_layout=True)
        try:
            for plot, group in zip(plots, ('A', 'D')):
                frequency, power, count = stitch(synthetic_tiles(group), group)
                known = {'A': (95800000, 150000000, 433920000),
                         'D': (868000000, 1800000000, 2450000000)}[group]
                peak_errors = []
                for tone in known:
                    window = np.flatnonzero(abs(frequency - tone) <= 100000)
                    measured = frequency[window[np.argmax(power[window])]]
                    peak_errors.append(float(abs(measured - tone)))
                checks = dict(no_coverage_gaps=bool(np.all(count > 0)),
                              tones_within_15kHz=bool(max(peak_errors) <= 15000))
                if not all(checks.values()):
                    raise AssertionError('Synthetic panorama check failed: ' + group)
                path = output / ('panorama_' + group + '_synthetic.npz')
                atomic_write(path, lambda stream: np.savez_compressed(
                    stream, frequency_hz=frequency, psd_fs2_per_hz=power,
                    coverage_count=count, synthetic=np.array(True)))
                sidecar(path)
                result['groups'][group] = dict(
                    bounds_hz=GROUPS[group], tiles=len(tile_centers(group)),
                    output_bins=len(frequency), max_tone_error_hz=max(peak_errors),
                    checks=checks, file=path.name, sha256=digest(path))
                plot.plot(frequency / 1e6, dbfs_per_hz(power), linewidth=0.6)
                plot.set(title='SYNTHETIC ONLY - antenna group ' + group,
                         xlabel='Frequency (MHz)', ylabel='PSD (dBFS/Hz)', ylim=(-150, -35))
                plot.grid(alpha=0.2)
            path = output / 'synthetic_panorama.png'
            figure.savefig(str(path), dpi=130)
            sidecar(path)
        finally:
            plt.close(figure)
        stream = EvidenceStream(output / 'synthetic_hour.jsonl', recent_limit=32)
        stats = StabilityStats()
        try:
            for second in range(3601):
                sample = dict(elapsed_s=second, rss_bytes=50000000 + second * 100,
                              temperature_c=60 + second / 3600, display_fps=40.0,
                              processing_status=0)
                stream.append(sample)
                stats.observe(sample)
        finally:
            result['synthetic_stream'] = stream.close()
        result['synthetic_stability'] = stats.finish(3600, True, 1000, 0)
        result['short_run_rejected'] = stats.finish(60, True, 1000, 0)['status'] == 'FAIL'
        if result['synthetic_stability']['status'] != 'PASS' or not result['short_run_rejected']:
            raise AssertionError('Synthetic stability criteria check failed')
        result['sources_sha256'] = {p.relative_to(ROOT).as_posix(): digest(p) for p in (
            ROOT / 'src/ps/sentinel/panorama.py', ROOT / 'src/ps/sentinel/stability.py',
            ROOT / 'src/ps/tests/test_f4_offline.py', Path(__file__).resolve())}
        result['status'] = 'PASS_SYNTHETIC_ONLY_BOARD_PENDING'
    except BaseException as error:
        result.update(status='FAIL', error=repr(error))
        raise
    finally:
        data = (json.dumps(result, indent=2, allow_nan=False) + '\n').encode('utf-8')
        atomic_write(result_path, lambda stream: stream.write(data))
        sidecar(result_path)
    print(str(result_path))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New local evidence directory')
    run(parser.parse_args().output)
