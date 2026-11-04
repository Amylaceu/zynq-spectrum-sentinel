"""Generate synthetic LCD previews without connecting to the development board."""
import argparse
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src/ps'))
from sentinel.ui_v3 import draw_ui_v3
from sentinel.ui_v3.theme import RGB, font
from sentinel.tracker_x5 import Track
from sentinel.release_support import write_result, sha


def sample_tracks():
    tracks = []
    for index, (frequency, label, score) in enumerate((
            (95.8e6, 'FM', .92), (96.2e6, 'AM-DSB', .73),
            (96.6e6, 'QPSK', .86), (95.45e6, 'QAM16', .31))):
        track = Track(index, frequency, 200000 if index == 0 else 120000,
                      12340-index*1820, 98.5 if index == 0 else 50, 100)
        track.label, track.confidence = label, score
        track.votes.extend([(label, score)]*5)
        tracks.append(track)
    return tracks


def compose(right, status):
    """Left region is labeled synthetic context, never a captured PL frame."""
    index = Image.new('L', (800, 480), 0)
    pen = ImageDraw.Draw(index)
    pen.fontmode = '1'
    pen.text((12, 10), 'OFFLINE / SYNTHETIC PREVIEW', font=font(20), fill=2)
    pen.text((12, 39), 'Left: PL region unchanged', font=font(14), fill=1)
    pen.text((12, 60), 'Right + bottom: proposed PS UI', font=font(14), fill=1)
    for y in (100, 140, 180, 220):
        pen.line((12, y, 548, y), fill=1)
    x = np.arange(534)
    peak = sum(amplitude*np.exp(-((x-center)/width)**2) for center, width, amplitude in
               ((95, 6, 82), (255, 11, 122), (410, 9, 72)))
    y = 214-peak-3*np.sin(x*.31)
    pen.line([(int(a+13), int(b)) for a, b in zip(x, y)], fill=3, width=1)
    pen.text((12, 237), 'ILLUSTRATIVE SPECTRUM / WATERFALL', font=font(12), fill=2)
    for row in range(267, 398):
        for center, width in ((108, 5), (268, 10), (423, 7)):
            pen.line((center-width, row, center+width, row), fill=3)
        if row % 5 == 0:
            pen.line((262, row, 274, row), fill=2)
    index.paste(Image.fromarray(right), (560, 0))
    index.paste(Image.fromarray(status), (0, 400))
    return Image.fromarray(np.asarray(RGB, dtype=np.uint8)[np.asarray(index)])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'report/figures/ui_v3')
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    tracks = sample_tracks()
    rng = np.random.default_rng(20261104)
    symbols = (rng.choice([-1, 1], 512)+1j*rng.choice([-1, 1], 512)
               +.1*(rng.normal(size=512)+1j*rng.normal(size=512)))
    base = dict(tracks=tracks, selected=2, iq=symbols, now=100, uptime_s=754,
                lo_hz=96050000, fps=29.0, frame=21984, temperature_c=58.3,
                pc_connected=True, model_status='SCORE UNCALIBRATED',
                events=('12:03:50 AMC 96.60M QPSK', '12:03:44 NEW 95.80M FM',
                        '12:03:41 MODE MONITOR'))
    scenes = [('SIG', dict(view='SIG')), ('TGT', dict(view='TGT')),
              ('STAT', dict(view='STAT', histogram={'FM': 24, 'QPSK': 17, 'AM-DSB': 8, '?': 4})),
              ('OTA_TX_ON', dict(view='STAT', demo_mode='OTA TX', tx_active=True,
                 tx_atten_db=52, demo_title='5 TEN MOD OTA', demo_remaining_s=43,
                 sent_label='QPSK', accuracy=(42, 50),
                 histogram={'QPSK': 17, 'FM': 9, 'QAM16': 8, 'AM-DSB': 6, '?': 10})),
              ('OTA_TX_DIM', dict(view='TGT', demo_mode='OTA TX', tx_active=True,
                 tx_atten_db=52, now=100.5, demo_title='6 QPSK RF+NOISE', demo_remaining_s=18)),
              ('SELFTEST', dict(view='SIG', demo_mode='SELFTEST', demo_title='1 RX STARTUP',
                 demo_remaining_s=8, selftest_checks=[('AD9361 ID', True), ('BITSTREAM', True),
                                                    ('TX 89.75dB', True), ('TEMP', None)]))]
    previews, digests = [], {}
    for name, changes in scenes:
        preview = compose(*draw_ui_v3(**dict(base, **changes)))
        path = args.output/(name+'.png')
        preview.save(path)
        digests[path.name] = sha(path)
        previews.append((name, preview))
    overview = Image.new('RGB', (1600, 1536), 'black')
    pen = ImageDraw.Draw(overview)
    for i, (name, preview) in enumerate(previews):
        x, y = (i % 2)*800, (i//2)*512
        pen.text((x+12, y+2), name+' / OFFLINE', font=font(20), fill='white')
        overview.paste(preview, (x, y+32))
    overview.save(args.output/'overview.png')
    digests['overview.png'] = sha(args.output/'overview.png')
    write_result(args.output/'preview_manifest.json', dict(status='OFFLINE_PREVIEW_ONLY',
        synthetic=True, board_accessed=False, ui_regions=[[560, 0, 240, 400], [0, 400, 800, 80]],
        palette_rgb=RGB, font_sizes=[20, 14, 12], target_label_size=24, files_sha256=digests,
        style_confirmation='PENDING', board_metrics='NOT_MEASURED'))
    print(args.output/'overview.png')


if __name__ == '__main__':
    main()
