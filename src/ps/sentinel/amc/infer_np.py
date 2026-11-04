"""Torch-free FP32/INT8 runtime; no RF operations on import or prediction."""
import json
from pathlib import Path

import numpy as np

from .contract import AMC_FS, CLASSES, COARSE_CLASSES, SCHEMA
from .features import complex_iq, frontend
from .fine import refine


def _quantized_matmul(x, weight, weight_scale):
    # One dynamic activation scale per capture, never shared between captures.
    axes = tuple(range(1, x.ndim))
    scale = np.max(np.abs(x), axis=axes).clip(1e-12)/127
    q = np.rint(x/scale.reshape((-1,)+(1,)*(x.ndim-1))).clip(-127, 127).astype(np.int32)
    # Explicit int32 conversion is essential: NumPy int8 @ int8 wraps in int8.
    output = q @ weight.T.astype(np.int32)
    return output.astype(np.float32)*scale.reshape((-1,)+(1,)*(output.ndim-1))*weight_scale


class Predictor:
    def __init__(self, model, precision='int8', refiner=None):
        if precision not in ('int8', 'fp32'):
            raise ValueError('precision must be int8 or fp32')
        with np.load(Path(model), allow_pickle=False) as archive:
            self.weights = {name:archive[name] for name in archive.files}
        self.metadata = json.loads(str(self.weights.pop('metadata')))
        if self.metadata['schema'] != SCHEMA:
            raise ValueError('Model frontend contract mismatch')
        if np.any(self.weights['feature_std'] <= 0):
            raise ValueError('Invalid normalization')
        self.precision = precision
        # Optional runtime backend; default preserves the frozen NumPy path.
        if refiner is not None and not callable(refiner):
            raise TypeError('refiner must be callable')
        self._refiner = refine if refiner is None else refiner

    def _layer(self, x, name):
        weights = self.weights
        if self.precision == 'fp32':
            result = x @ weights[name+'.weight'].reshape(weights[name+'.weight'].shape[0], -1).T
        else:
            weight = weights[name+'.weight.int8']
            result = _quantized_matmul(x, weight.reshape(weight.shape[0], -1), weights[name+'.weight.scale'])
        return result+weights[name+'.bias']

    def logits(self, front, features):
        x = np.asarray(front, dtype=np.float32)
        for name, kernel in (('conv1', 7), ('conv2', 5), ('conv3', 3)):
            # Same valid, stride=2 convolution as torch Conv1d.
            windows = np.lib.stride_tricks.sliding_window_view(x, kernel, axis=2)[:, :, ::2, :]
            matrix = windows.transpose(0, 2, 1, 3).reshape(len(x), windows.shape[2], -1)
            x = np.maximum(self._layer(matrix, name), 0).transpose(0, 2, 1)
        spectral = x.mean(axis=2)
        standardized = (features-self.weights['feature_mean'])/self.weights['feature_std']
        hoc = np.maximum(self._layer(standardized, 'hoc_fc'), 0)
        fused = np.maximum(self._layer(np.concatenate((spectral, hoc), axis=1), 'fuse'), 0)
        return self._layer(fused, 'output')

    def predict(self, iq, fs=AMC_FS):
        if fs != AMC_FS:
            raise ValueError('Training/deployment sample rates must both be 480 kSPS')
        iq = complex_iq(iq)
        front, features = frontend(iq)
        logits = self.logits(front, features)
        probabilities = np.exp(logits-logits.max(axis=1, keepdims=True))
        probabilities /= probabilities.sum(axis=1, keepdims=True)
        result = []
        direct = {'BPSK':'BPSK', '2FSK':'2FSK', 'GFSK':'GFSK', 'OOK':'OOK', 'AM':'AM-DSB', 'FM':'FM'}
        for index, coarse_index in enumerate(probabilities.argmax(axis=1)):
            family = COARSE_CLASSES[int(coarse_index)]
            confidence = float(probabilities[index, coarse_index])
            detail = None
            if family in ('PSK-high', 'QAM'):
                detail = self._refiner(iq[index], family, fs)
                label = detail['label']
                confidence *= detail['confidence']
            else:
                label = direct[family]
            result.append(dict(label=label, class_index=CLASSES.index(label),
                               coarse=family, coarse_index=int(coarse_index),
                               confidence=confidence, detail=detail,
                               top5=[dict(label=COARSE_CLASSES[int(i)],
                                          score=float(probabilities[index, i]))
                                     for i in np.argsort(-probabilities[index], kind='stable')[:5]],
                               top5_scope='coarse8_softmax'))
        return result
