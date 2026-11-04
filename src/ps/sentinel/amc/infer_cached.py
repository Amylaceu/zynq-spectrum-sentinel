"""Opt-in X4 runtime candidate with immutable, prepared INT32 weights.

The evaluated Predictor remains the deployment default. This class changes no
model, activation scale, arithmetic precision, frontend or refinement logic.
It trades persistent RAM for avoiding six weight conversions per prediction.
An explicit exact-fp32 backend can use NumPy's floating-point GEMM after an
integer range proof: every product and every possible partial sum fits exactly
in FP32's 24-bit significand. This is not an INT32 accumulator benchmark.
Board latency acceptance is separate from PC equivalence/benchmark results.
"""
import numpy as np

from .infer_np import Predictor


def prepare_exact_weight(weight):
    """Prove all signed INT8 dot products of activations [-127,127] exact."""
    if weight.dtype != np.int8 or weight.ndim != 2 or not weight.shape[1]:
        raise ValueError('Expected a nonempty 2D INT8 weight matrix')
    bound = int(np.abs(weight.astype(np.int64)).sum(axis=1).max())*127
    if bound > 2**24:
        raise ValueError('FP32 exact integer accumulation range exceeded')
    return weight.T.astype(np.float32)


class CachedPredictor(Predictor):
    """Load once, predict repeatedly; model weights are read-only after load."""

    def __init__(self, model, precision='int8', accumulator='int32'):
        if accumulator not in ('int32', 'exact-fp32'):
            raise ValueError('accumulator must be int32 or exact-fp32')
        super().__init__(model, precision)
        self.accumulator = accumulator
        self._prepared = {}
        for name in ('conv1', 'conv2', 'conv3', 'hoc_fc', 'fuse', 'output'):
            weight = self.weights[name+'.weight.int8']
            matrix = weight.reshape(weight.shape[0], -1)
            prepared = (matrix.T.astype(np.int32) if accumulator == 'int32'
                        else prepare_exact_weight(matrix))
            prepared.setflags(write=False)
            self._prepared[name] = prepared
        for weight in self.weights.values():
            weight.setflags(write=False)

    @property
    def cache_bytes(self):
        return sum(weight.nbytes for weight in self._prepared.values())

    def _layer(self, x, name):
        if self.precision == 'fp32':
            return super()._layer(x, name)
        # Preserve the reference operation order and one scale per capture.
        axes = tuple(range(1, x.ndim))
        scale = np.max(np.abs(x), axis=axes).clip(1e-12)/127
        q = np.rint(x/scale.reshape((-1,)+(1,)*(x.ndim-1))).clip(-127, 127).astype(np.int32)
        if self.accumulator == 'exact-fp32':
            q = q.astype(np.float32)
        output = q @ self._prepared[name]
        result = (output.astype(np.float32)
                  * scale.reshape((-1,)+(1,)*(output.ndim-1))
                  * self.weights[name+'.weight.scale'])
        return result+self.weights[name+'.bias']
