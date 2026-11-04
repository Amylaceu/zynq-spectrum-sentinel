"""Explicit opt-in native timing recovery; default Predictor stays portable.

Build native/gardner.c for the execution device, then pass its absolute library
path. Missing/incompatible libraries fail explicitly, never silently fallback.
The trained model, frontend, CNN, thresholds and CFO/matched filter are intact.
"""
import ctypes
from pathlib import Path

import numpy as np

from .fine import refine
from .infer_np import Predictor


class NativeGardner:
    def __init__(self, library):
        path = Path(library).resolve(strict=True)
        self.library_path = path
        self._lib = ctypes.CDLL(str(path))
        self._lib.sentinel_gardner_abi.argtypes = []
        self._lib.sentinel_gardner_abi.restype = ctypes.c_int
        if self._lib.sentinel_gardner_abi() != 1:
            raise ValueError('Unsupported Gardner native ABI')
        pointer = ctypes.POINTER(ctypes.c_double)
        self._run = self._lib.sentinel_gardner
        self._run.argtypes = [pointer, ctypes.c_size_t, ctypes.c_double,
                              ctypes.c_double, pointer, ctypes.c_size_t]
        self._run.restype = ctypes.c_int

    def __call__(self, x, sps):
        x = np.ascontiguousarray(x, dtype=np.complex128)
        if x.ndim != 1 or not 256 <= len(x) <= 1048576 or not np.isfinite(x).all():
            raise ValueError('Expected finite one-dimensional complex samples')
        sps = float(sps)
        if not np.isfinite(sps) or not 4 <= sps <= 16:
            raise ValueError('sps must be finite and in [4,16]')
        offsets = np.arange(0, sps, .25)
        # The reference computes identical scores four times for each integer
        # offset. Cache identical slices, preserving first-maximum tie breaking.
        scores, cached = [], {}
        stride = max(1, int(round(sps)))
        for offset in offsets:
            index = int(offset)
            if index not in cached:
                cached[index] = np.mean(np.abs(x[index+32:-32:stride])**2)
            scores.append(cached[index])
        phase = float(offsets[int(np.argmax(scores))])
        out = np.empty(len(x), dtype=np.complex128)
        pointer = ctypes.POINTER(ctypes.c_double)
        count = self._run(x.ctypes.data_as(pointer), len(x), sps, phase,
                          out.ctypes.data_as(pointer), len(out))
        if count < 0:
            raise RuntimeError('Gardner native bounds/ABI failure: %d' % count)
        return out[:count].copy()


class NativePredictor(Predictor):
    def __init__(self, model, library, precision='int8'):
        self.timing_recovery = NativeGardner(library)
        super().__init__(model, precision, refiner=self._native_refine)

    def _native_refine(self, iq, family, fs):
        return refine(iq, family, fs, timing_recovery=self.timing_recovery)
