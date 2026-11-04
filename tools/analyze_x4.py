"""Recompute X4 metrics from saved holdout predictions; never trust PASS flags."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.ps.sentinel.amc.contract import CLASSES, COARSE_MAP
from x2_transport import verified, sha, write_evidence


def metrics(truth, snr, pred, coarse):
    if not (truth.shape == snr.shape == pred.shape == coarse.shape) or truth.ndim != 1:
        raise ValueError('Prediction arrays must have identical one-dimensional shapes')
    if np.any((truth < 0)|(truth > 9)|(pred < 0)|(pred > 9)|(coarse < 0)|(coarse > 7)):
        raise ValueError('Invalid class index')
    mapping = np.asarray(COARSE_MAP)
    if not np.array_equal(mapping[pred], coarse):
        raise ValueError('Fine predictions must stay within predicted coarse family')
    curve, coarse_curve, confusion10 = {}, {}, np.zeros((10,10), dtype=np.int64)
    for s in range(-4, 21, 2):
        selected = snr == s
        if not selected.any() or len(set(truth[selected].tolist())) != 10:
            raise ValueError('Every SNR must include all ten classes')
        curve[str(s)] = float(np.mean(pred[selected] == truth[selected]))
        coarse_curve[str(s)] = float(np.mean(coarse[selected] == mapping[truth[selected]]))
    selected = snr == 10
    np.add.at(confusion10, (truth[selected], pred[selected]), 1)
    recall = np.diag(confusion10)/confusion10.sum(1)
    return dict(accuracy_vs_snr=curve, coarse_accuracy_vs_snr=coarse_curve,
                overall=float(np.mean(truth == pred)), confusion_snr10=confusion10.tolist(),
                recall_snr10={name:float(recall[i]) for i,name in enumerate(CLASSES)})


def analyze(attempt):
    tag = 'x4_pc_r'+str(attempt)
    execution = verified(ROOT/'board/measurements'/(tag+'.json'))
    evaluation_path = ROOT/'board/measurements'/(tag+'_evaluation.json')
    evaluation = verified(evaluation_path)
    if execution['smoke_only'] or not execution['frozen_sources_unchanged']:
        raise ValueError('Production round with intact frozen sources required')
    if sha(evaluation_path) != execution['evaluation_sha256']:
        raise ValueError('Execution/evaluation mismatch')
    data = ROOT/'data/synthetic/amc_v2'
    manifest = verified(data/'manifest.json')
    if manifest['per_cell'] != 2000 or manifest['smoke_only'] or manifest['fs'] != 480000 or manifest['capture_len'] != 4096:
        raise ValueError('Production dataset contract mismatch')
    ids = {}
    for split in ('train','val','test'):
        ids[split] = np.load(data/split/'sample_id.npy')
        if len(np.unique(ids[split])) != len(ids[split]):
            raise ValueError('Duplicate sample IDs')
    all_ids = np.concatenate(list(ids.values()))
    if len(np.unique(all_ids)) != 260000:
        raise ValueError('Sample leakage across splits or wrong total')
    for split, expected in (('train', 208000), ('val', 26000), ('test', 26000)):
        if len(ids[split]) != expected:
            raise ValueError('Incorrect split size: '+split)
        for key in ('sample_id', 'label', 'snr'):
            rel = split+'/'+key+'.npy'
            if sha(data/rel) != manifest['files'][rel]:
                raise ValueError('Dataset evidence changed: '+rel)
    work = ROOT/'build/work'/tag
    for rel, digest in execution['source_sha256'].items():
        if sha(work/'source'/rel) != digest:
            raise ValueError('Frozen source changed: '+rel)
    model_path = work/'model/amc_l1_int8.npz'
    if sha(model_path) != execution['export_sha256']:
        raise ValueError('Export changed after evaluation')
    predictions_path = evaluation_path.with_suffix('.npz')
    if sha(predictions_path) != evaluation['predictions_sha256']:
        raise ValueError('Prediction archive digest mismatch')
    computed = {}
    with np.load(predictions_path, allow_pickle=False) as archive:
        if not np.array_equal(archive['sample_id'], ids['test']):
            raise ValueError('Predictions not in original holdout order')
        for key in ('truth', 'snr'):
            expected = np.load(data/'test'/('label.npy' if key == 'truth' else 'snr.npy'))
            if not np.array_equal(archive[key], expected):
                raise ValueError('Holdout truth changed')
        for precision in ('fp32','int8'):
            computed[precision] = metrics(archive['truth'], archive['snr'], archive[precision], archive[precision+'_coarse'])
            for key in ('accuracy_vs_snr','coarse_accuracy_vs_snr','confusion_snr10','recall_snr10'):
                if computed[precision][key] != evaluation['metrics'][precision][key]:
                    raise ValueError('Recorded metric differs from raw predictions: '+key)
    drops = {s:computed['fp32']['accuracy_vs_snr'][s]-computed['int8']['accuracy_vs_snr'][s] for s in computed['fp32']['accuracy_vs_snr']}
    values = computed['int8']
    gates = dict(accuracy10=values['accuracy_vs_snr']['10'] >= .88,
                 coarse10=values['coarse_accuracy_vs_snr']['10'] >= .95,
                 qpsk_recall=values['recall_snr10']['QPSK'] >= .8,
                 psk8_recall=values['recall_snr10']['8PSK'] >= .8,
                 quantization_drop_all_snrs=max(drops.values()) <= .01,
                 quantization_drop_overall=computed['fp32']['overall']-values['overall'] <= .01)
    board_path = ROOT/'board/measurements'/('x4_board_r'+str(attempt)+'.json')
    board = verified(board_path) if board_path.exists() else None
    if board:
        if board['round_evidence_sha256'] != sha(ROOT/'board/measurements'/(tag+'.json')):
            raise ValueError('Board benchmark belongs to a different round')
        if board['smoke_only'] or board['fs'] != 480000 or board['capture_len'] != 4096:
            raise ValueError('Invalid board inference contract')
        rows = board['rows']
        times = np.asarray([row['elapsed_ms'] for row in rows])
        if (len(times) != 50 or not np.isfinite(times).all() or np.any(times <= 0)
                or len({row['sample_id'] for row in rows}) != 50):
            raise ValueError('Invalid or duplicate board timings')
        latency_summary = dict(median_ms=float(np.median(times)), max_ms=float(times.max()),
                               all_under_100ms=bool(np.all(times <= 100)))
        if any(board[key] != value for key, value in latency_summary.items()):
            raise ValueError('Recorded board summary differs from individual timings')
        gates['board_latency'] = latency_summary['all_under_100ms']
        # ARM NumPy must produce the same labels as the frozen PC runtime.
        # Timings alone do not establish portable inference correctness.
        with np.load(predictions_path, allow_pickle=False) as archive:
            lookup = {int(sample): index for index, sample in enumerate(archive['sample_id'])}
            selected = np.concatenate([
                np.flatnonzero((archive['truth'] == label) & (archive['snr'] == 10))[:5]
                for label in range(10)])
            expected_ids = [int(sample) for sample in archive['sample_id'][selected]]
            if [row['sample_id'] for row in rows] != expected_ids:
                raise ValueError('Board benchmark did not use the prescribed holdout captures')
            parity = []
            for row in rows:
                index = lookup[row['sample_id']]
                if row['label'] != int(archive['truth'][index]):
                    raise ValueError('Board capture label differs from original holdout')
                parity.append(row['predicted'] == CLASSES[int(archive['int8'][index])])
            gates['board_prediction_parity'] = bool(all(parity))
    else:
        gates['board_latency'] = False
        gates['board_prediction_parity'] = False
    result = dict(step='X4', attempt=attempt, status='PASS' if all(gates.values()) else 'FAIL',
                  metrics=computed, quantization_drop_pp={s:100*v for s,v in drops.items()},
                  gates=gates, board=board, split_counts={k:len(v) for k,v in ids.items()},
                  limitation='Synthetic occupied-bandwidth SNR; not OTA accuracy or calibrated confidence',
                  evidence_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in
                      [evaluation_path, predictions_path, ROOT/'board/measurements'/(tag+'.json')]+([board_path] if board else [])})
    out = ROOT/'board/measurements'/('x4_analysis_r'+str(attempt)+'.json')
    write_evidence(out, result)
    print(json.dumps(dict(status=result['status'], gates=gates, int8_snr10=values['accuracy_vs_snr']['10'])))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--attempt', type=int, choices=(1,2,3), required=True)
    analyze(p.parse_args().attempt)
