"""Verify SCAP evidence, evaluate frozen model, save reproducible noise curves."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src/ps'))
from sentinel.amc.contract import CLASSES
from sentinel.amc.infer_np import Predictor
from sentinel.capture_x5 import decode_packet, select_channel
from sentinel.f3_evaluate import add_noise, scores
from x2_transport import sha, verified, write_evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, default=ROOT/'board/measurements/f3_capture_r1')
    parser.add_argument('--out', type=Path, default=ROOT/'board/measurements/f3_evaluation_r1')
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    record = verified(args.capture/'result.json')
    if (record['status'] != 'PASS' or record['stop_attenuation_db'] != [89.75, 89.75]
            or record['gpio_after_close'] or record['source_after_close']):
        raise ValueError('Incomplete capture/safe stop')
    wave_dir = ROOT/'data/reference/f3_ota'
    manifest = verified(wave_dir/'manifest.json')
    if len(record['modulation_captures']) != 10:
        raise ValueError('Missing class')
    batches, simulation, truth, checks = [], [], [], []
    for index, item in enumerate(record['modulation_captures']):
        path = args.capture/item['filename']
        if item['index'] != index or item['label'] != CLASSES[index] or sha(path) != item['sha256']:
            raise ValueError('Capture provenance mismatch')
        with np.load(path, allow_pickle=False) as data:
            words, health = data['words'], data['readbacks']
            if words.shape != (50, 4104) or health.shape != (50, 3) or int(data['fs_hz']) != 480000:
                raise ValueError('Capture dimensions')
            if not np.isfinite(health).all() or np.max(health[:, :2]) > -30 or np.any(health[:, 2] < 40):
                raise ValueError('Unsafe RF readback')
            packets = [decode_packet(a, select_channel(240000), 3) for a in words]
        ticks = [p['timestamp_cycles'] for p in packets]
        if any(b <= a for a, b in zip(ticks, ticks[1:])):
            raise ValueError('Non-monotonic SCAP timestamps')
        iq = np.stack([p['iq'] for p in packets])
        batches.append(iq)
        checks.append(dict(label=item['label'], sha256=item['sha256'], count=len(iq),
            unique_iq_hashes=len({hashlib.sha256(x.tobytes()).hexdigest() for x in iq}),
            max_rssi_dbm=float(health[:, :2].max()), min_atten_db=float(health[:, 2].min()),
            timestamp_first=ticks[0], timestamp_last=ticks[-1]))
        entry = manifest['waveforms'][index]
        wave = wave_dir/entry['filename']
        if sha(wave) != entry['sha256'] or item['tx_waveform_sha256'] != entry['sha256']:
            raise ValueError('Transmit waveform digest mismatch')
        with np.load(wave, allow_pickle=False) as data:
            base = data['base']
        # Matched generator only: excludes TX interpolation, RF and PL PFB.
        simulation.append(np.stack([base[(np.arange(4096)+k*521) % len(base)] for k in range(50)]))
        truth.extend([index]*50)
    labels = np.asarray(truth, dtype=np.int16)
    model = ROOT/'src/ps/models/weights/amc_v2/round_3/model.npz'
    predictor = Predictor(model)
    args.out.mkdir(parents=True)
    result = dict(status='STARTED', started_utc=datetime.now(timezone.utc).isoformat(),
        model_sha256=sha(model), capture_result_sha256=sha(args.capture/'result.json'),
        reference_manifest_sha256=sha(wave_dir/'manifest.json'), capture_checks=checks,
        labels=list(CLASSES), seed=431000,
        scope='Post-capture AWGN relative to total measured IQ power; intrinsic RF noise retained. '
              '50 successive cyclic waveform windows/class, not 50 independent RF waveform trials.',
        simulation_scope='Same seeded base generator; excludes TX interpolation, RF and PL PFB.',
        curves={})
    raw_predictions = {}
    for dataset, signal in (('ota', np.concatenate(batches)), ('simulation', np.concatenate(simulation))):
        curve = []
        for snr in [None]+list(range(-4, 21, 2)):
            x = signal if snr is None else add_noise(signal, snr, np.random.default_rng(431000+int(snr)+4))
            predictions = []
            for begin in range(0, len(x), 25):
                predictions.extend(predictor.predict(x[begin:begin+25], fs=480000))
            predicted = np.asarray([p['class_index'] for p in predictions], dtype=np.int16)
            point = dict(injected_reference_db=snr, **scores(labels, predicted))
            curve.append(point)
            raw_predictions[dataset+'_'+str(snr)] = predicted
            print(dataset, snr, point['accuracy_10'], point['accuracy_8'], flush=True)
        result['curves'][dataset] = curve
        write_evidence(args.out/(dataset+'_curve.json'), dict(points=curve, scope=result['scope']))
    np.savez_compressed(args.out/'predictions.npz', truth=labels, **raw_predictions)
    pred_path = args.out/'predictions.npz'
    pred_path.with_suffix('.npz.sha256').write_text(sha(pred_path)+'  predictions.npz\n')
    result['predictions_sha256'] = sha(pred_path)
    at10 = next(x for x in result['curves']['ota'] if x['injected_reference_db'] == 10)
    result.update(status='PASS', metric_10class_pass=at10['accuracy_10'] >= .8,
                  metric_8family_pass=at10['accuracy_8'] >= .9,
                  finished_utc=datetime.now(timezone.utc).isoformat())
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 5))
    for dataset, style in (('ota', '-o'), ('simulation', '--s')):
        points = result['curves'][dataset][1:]
        for key, title in (('accuracy_10', '10 classes'), ('accuracy_8', '8 families')):
            ax.plot([x['injected_reference_db'] for x in points], [100*x[key] for x in points],
                    style, label=dataset+' / '+title)
    ax.set(xlabel='Measured total IQ power / added AWGN (dB)', ylabel='Accuracy (%)', ylim=(0, 100))
    ax.grid(True); ax.legend(); fig.tight_layout()
    fig.savefig(args.out/'accuracy.png', dpi=170); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    from sentinel.amc.contract import COARSE_CLASSES
    for ax, key, names in zip(axes, ('confusion_10', 'confusion_8'), (CLASSES, COARSE_CLASSES)):
        ax.imshow(at10[key], vmin=0, cmap='Blues')
        ax.set_xticks(range(len(names)), names, rotation=75)
        ax.set_yticks(range(len(names)), names)
        ax.set(xlabel='Predicted', ylabel='Transmitted', title='Added noise reference 10 dB')
    fig.tight_layout(); fig.savefig(args.out/'confusion_10db.png', dpi=170); plt.close(fig)
    result['plots'] = {p.name:sha(p) for p in args.out.glob('*.png')}
    for p in args.out.glob('*.png'):
        p.with_suffix('.png.sha256').write_text(sha(p)+'  '+p.name+'\n')
    write_evidence(args.out/'result.json', result)


if __name__ == '__main__':
    main()
