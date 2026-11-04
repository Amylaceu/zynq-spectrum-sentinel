"""Evaluate frozen holdout once per round; predictions and source hashes saved."""
import argparse
import json
from pathlib import Path
import time

import numpy as np
import torch

from .amc_l1 import AMCLevel1
from .make_dataset_v2 import sha
from src.ps.sentinel.amc.contract import CLASSES, COARSE_MAP, SCHEMA
from src.ps.sentinel.amc.features import frontend
from src.ps.sentinel.amc.infer_np import Predictor


def evaluate(data, checkpoint, exported, out, threads=8):
    torch.set_num_threads(threads)
    data, checkpoint, exported, out = map(Path, (data, checkpoint, exported, out))
    if out.exists() or out.with_suffix('.npz').exists():
        raise FileExistsError('Preserve previous holdout evaluation')
    manifest = json.loads((data/'manifest.json').read_text())
    if manifest['schema'] != SCHEMA:
        raise ValueError('Dataset contract mismatch')
    for key in ('iq', 'front', 'features', 'label', 'snr', 'sample_id'):
        rel = 'test/'+key+'.npy'
        if sha(data/rel) != manifest['files'][rel]:
            raise ValueError('Test digest mismatch: '+rel)
    chosen = torch.load(checkpoint, map_location='cpu', weights_only=True)
    if chosen['dataset_sha256'] != sha(data/'manifest.json'):
        raise ValueError('Checkpoint dataset mismatch')
    model = AMCLevel1().eval()
    model.load_state_dict(chosen['state_dict'])
    runtime = Predictor(exported, 'fp32')
    if runtime.metadata['checkpoint_sha256'] != sha(checkpoint):
        raise ValueError('Export checkpoint mismatch')
    arrays = {name:np.load(data/'test'/(name+'.npy'), mmap_mode='r') for name in
              ('iq', 'front', 'features', 'label', 'snr', 'sample_id')}
    predictions, coarse_predictions = {}, {}
    parity_max = 0.
    start = time.monotonic()
    for precision in ('fp32', 'int8'):
        runtime.precision = precision
        fine, coarse = [], []
        for begin in range(0, len(arrays['iq']), 128):
            section = slice(begin, begin+128)
            # Recompute deployment preprocessing; cached train frontend cannot
            # silently differ from what board inference does.
            front, features = frontend(arrays['iq'][section])
            if not np.allclose(front, arrays['front'][section], atol=1e-6) or not np.allclose(features, arrays['features'][section], atol=1e-6):
                raise ValueError('Cached/deployment preprocessing differs')
            if precision == 'fp32':
                with torch.inference_mode():
                    reference = model(torch.from_numpy(front), torch.from_numpy(features)).numpy()
                difference = float(np.max(np.abs(reference-runtime.logits(front, features))))
                parity_max = max(parity_max, difference)
                if not np.allclose(reference, runtime.logits(front, features), rtol=2e-4, atol=2e-4):
                    raise ValueError('FP32 NumPy/torch mismatch')
            for result in runtime.predict(arrays['iq'][section]):
                fine.append(result['class_index']); coarse.append(result['coarse_index'])
            if begin % 2048 == 0:
                print(json.dumps(dict(precision=precision, completed=len(fine), elapsed_s=time.monotonic()-start)), flush=True)
        predictions[precision], coarse_predictions[precision] = np.asarray(fine), np.asarray(coarse)
    labels, snrs = arrays['label'], arrays['snr']
    coarse_truth = np.asarray(COARSE_MAP)[labels]
    metrics = {}
    for precision in ('fp32', 'int8'):
        pred, coarse = predictions[precision], coarse_predictions[precision]
        curve, coarse_curve = {}, {}
        for snr in np.unique(snrs):
            mask = snrs == snr
            curve[str(int(snr))] = float(np.mean(pred[mask] == labels[mask]))
            coarse_curve[str(int(snr))] = float(np.mean(coarse[mask] == coarse_truth[mask]))
        confusion = np.zeros((10, 10), dtype=np.int64)
        confusion10 = np.zeros_like(confusion)
        np.add.at(confusion, (labels, pred), 1)
        mask = snrs == 10
        np.add.at(confusion10, (labels[mask], pred[mask]), 1)
        recalls = {CLASSES[i]:float(confusion10[i, i]/confusion10[i].sum()) for i in range(10)}
        metrics[precision] = dict(accuracy_vs_snr=curve, coarse_accuracy_vs_snr=coarse_curve,
                                  confusion=confusion.tolist(), confusion_snr10=confusion10.tolist(),
                                  recall_snr10=recalls)
    drop = metrics['fp32']['accuracy_vs_snr']['10']-metrics['int8']['accuracy_vs_snr']['10']
    gates = dict(accuracy10=metrics['int8']['accuracy_vs_snr']['10'] >= .88,
                 coarse10=metrics['int8']['coarse_accuracy_vs_snr']['10'] >= .95,
                 qpsk_recall=metrics['int8']['recall_snr10']['QPSK'] >= .8,
                 psk8_recall=metrics['int8']['recall_snr10']['8PSK'] >= .8,
                 quantization_drop=drop <= .01)
    out.parent.mkdir(parents=True, exist_ok=True)
    archive = out.with_suffix('.npz')
    with archive.open('xb') as stream:
        np.savez_compressed(stream, truth=labels, snr=snrs, sample_id=arrays['sample_id'],
                            fp32=predictions['fp32'], int8=predictions['int8'],
                            fp32_coarse=coarse_predictions['fp32'], int8_coarse=coarse_predictions['int8'])
    result = dict(schema=SCHEMA, smoke_only=manifest['smoke_only'], metrics=metrics,
                  gates=gates, pc_status='PASS' if all(gates.values()) and not manifest['smoke_only'] else 'FAIL_OR_SMOKE',
                  board_latency='NOT_MEASURED', quantization_drop_pp=100*drop,
                  torch_numpy_max_absolute_error=parity_max, elapsed_s=time.monotonic()-start,
                  source_sha256={str(p):sha(p) for p in (data/'manifest.json', checkpoint, exported)},
                  predictions_sha256=sha(archive))
    out.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    for p in (out, archive):
        Path(str(p)+'.sha256').write_text(sha(p)+'  '+p.name+'\n', encoding='ascii')
    print('EVAL_COMPLETE '+json.dumps(dict(gates=gates, snr10=metrics['int8']['accuracy_vs_snr']['10'])), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True)
    parser.add_argument('--l1', required=True)
    parser.add_argument('--export', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--threads', type=int, default=8)
    args = parser.parse_args()
    evaluate(args.data, args.l1, args.export, args.out, args.threads)
