"""Independently recompute a real finite sweep, export PNG and desktop screenshot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'src/ps'), str(ROOT/'tools/host')]
from sentinel.panorama import welch_psd, stitch, dbfs_per_hz
from sentinel.panorama_capture import write_json, seal
from sentinel_host.panorama_data import load_panorama


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--result', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    record, frequency, db, count = load_panorama(args.result)
    args.output.mkdir(parents=True, exist_ok=False)
    tiles, errors = [], []
    iq_tiles = 0
    for tile in record['tiles']:
        with np.load(args.result.parent/tile['file'], allow_pickle=False) as raw:
            if 'rx1_iq_counts' in raw:
                words = raw['rx1_iq_counts']
                if words.dtype != np.dtype('<i2') or words.shape != (record.get('samples_per_tile', 131072), 2):
                    raise ValueError('Unexpected native IQ format')
                f, power = welch_psd(words[:, 0].astype(float)+1j*words[:, 1].astype(float))
                if not np.array_equal(f, raw['baseband_hz']):
                    raise ValueError('Baseband bins differ')
                errors.append(float(np.max(np.abs(power-raw['psd_fs2_per_hz']))))
                if not np.allclose(power, raw['psd_fs2_per_hz'], rtol=1e-10, atol=1e-24):
                    raise ValueError('Independent IQ-to-PSD recomputation differs')
                iq_tiles += 1
            else:
                if record.get('raw_iq_saved') is not False:
                    raise ValueError('Missing declared IQ evidence')
                f, power = raw['baseband_hz'], raw['psd_fs2_per_hz']
            tiles.append((int(raw['actual_lo_hz']), f, power))
    f, power, counts = stitch(tiles, record['group'])
    if not (np.array_equal(f, frequency) and np.array_equal(counts, count)
            and np.allclose(dbfs_per_hz(power), db, rtol=1e-10, atol=1e-10, equal_nan=True)):
        raise ValueError('Panorama recomputation differs')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(16, 5), layout='constrained')
    ax.plot(frequency/1e6, db, lw=.6, color='#167f90')
    ax.set(xlabel='Frequency (MHz)', ylabel='PSD (dBFS/Hz)',
           title='Measured RX1A panorama (%s) | finite snapshots | uncalibrated AGC/antenna' % record['group'])
    ax.grid(alpha=.2)
    if record['group'] == 'A':
        for lo, hi, name in [(87, 108, 'FM reference'), (136, 174, 'VHF reference'),
                             (400, 470, 'UHF reference')]:
            ax.axvspan(lo, hi, alpha=.08, color='orange')
            ax.text((lo+hi)/2, .98, name, transform=ax.get_xaxis_transform(),
                    ha='center', va='top', fontsize=8)
    ax.set_xlim(frequency[0]/1e6, frequency[-1]/1e6)
    png = args.output/'panorama.png'
    fig.savefig(png, dpi=160)
    plt.close(fig)
    seal(png)
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PySide6 import QtCore, QtGui, QtWidgets
    from sentinel_host.shell import Window
    from sentinel_host.theme import configure
    app = QtWidgets.QApplication([])
    for directory in QtCore.QStandardPaths.standardLocations(QtCore.QStandardPaths.FontsLocation):
        for name in ('msyh.ttc', 'msyhbd.ttc', 'segoeui.ttf', 'consola.ttf'):
            font = Path(directory)/name
            if font.is_file():
                QtGui.QFontDatabase.addApplicationFont(str(font))
    configure(app)
    window = Window()
    window.load_panorama(str(args.result.resolve()))
    window.show()
    app.processEvents()
    screenshot = args.output/'desktop_panorama.png'
    window.grab().save(str(screenshot))
    seal(screenshot)
    window.close()
    write_json(args.output/'analysis.json', dict(status=(
        'PASS_INDEPENDENT_RECOMPUTATION' if iq_tiles == len(tiles) else 'PASS_PSD_STITCH_RECOMPUTATION'),
        group=record['group'], tiles=len(tiles), full_group=record['full_group'],
        missing_bins=int(np.count_nonzero(count == 0)), bins=len(count),
        iq_recomputed_tiles=iq_tiles, psd_max_abs_error=max(errors) if errors else None,
        gui_source='VERIFIED_REAL_STORED_SWEEP',
        gui_hardware_connected=False, source_result_sha256=hashlib.sha256(args.result.read_bytes()).hexdigest(),
        continuous_dma_certified=False, one_hour_stability='DEFERRED_BY_USER',
        images=[png.name, screenshot.name]))
    print('F4_ANALYSIS_PASS', flush=True)


if __name__ == '__main__':
    main()
