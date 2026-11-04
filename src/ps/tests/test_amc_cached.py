"""Opt-in runtime equivalence; no training, board access or model mutation."""
from pathlib import Path

import numpy as np
import pytest

from sim.golden.siggen import gen_mod
from src.ps.sentinel.amc.features import frontend
from src.ps.sentinel.amc.infer_np import Predictor, _quantized_matmul
from src.ps.sentinel.amc.infer_cached import CachedPredictor, prepare_exact_weight

MODEL = Path(__file__).resolve().parents[1]/'models/weights/amc_v2/round_3/model.npz'


@pytest.mark.parametrize('precision', ['int8', 'fp32'])
@pytest.mark.parametrize('accumulator', ['int32', 'exact-fp32'])
def test_logits_exact_for_mixed_gain_and_single_or_batch(precision, accumulator):
    reference = Predictor(MODEL, precision)
    candidate = CachedPredictor(MODEL, precision, accumulator)
    iq = np.stack([gen_mod('FM',4096,8,fs=480000,seed=7),
                   gen_mod('QPSK',4096,8,fs=480000,seed=19)*.001])
    front, features = frontend(iq)
    for batch in (slice(None), slice(0,1), slice(1,2)):
        np.testing.assert_array_equal(candidate.logits(front[batch],features[batch]),
                                      reference.logits(front[batch],features[batch]))
    assert 0 < candidate.cache_bytes < 64*1024
    assert all(not item.flags.writeable for item in candidate._prepared.values())


@pytest.mark.parametrize('label', ['FM','QPSK','8PSK','16QAM','64QAM'])
def test_complete_prediction_preserves_refinement(label):
    reference = Predictor(MODEL)
    candidate = CachedPredictor(MODEL, accumulator='exact-fp32')
    iq = gen_mod(label,4096,8,fs=480000,seed=27)
    left,right = reference.predict(iq)[0],candidate.predict(iq)[0]
    for key in ('label','class_index','coarse','coarse_index','confidence'):
        assert left[key] == right[key]
    if left['detail'] is None:
        assert right['detail'] is None
    else:
        assert left['detail'].keys() == right['detail'].keys()
        for key in left['detail']:
            np.testing.assert_array_equal(left['detail'][key],right['detail'][key])


def test_exact_fp32_dot_at_full_scale_and_cancellation():
    rng = np.random.default_rng(631)
    weight = rng.integers(-128,128,(8,1024),dtype=np.int8)
    x = rng.integers(-127,128,(2,7,1024)).astype(np.float32)
    x[0,0] = 127
    actual = (x @ prepare_exact_weight(weight)).astype(np.int32)
    np.testing.assert_array_equal(actual,x.astype(np.int32) @ weight.T.astype(np.int32))
    with pytest.raises(ValueError,match='range exceeded'):
        prepare_exact_weight(np.full((1,1040),-128,dtype=np.int8))


def test_scale_and_overflow_contract():
    x = np.full((1,2,40),127,dtype=np.float32)
    weight = np.full((3,40),127,dtype=np.int8)
    exact = x @ prepare_exact_weight(weight)
    np.testing.assert_array_equal(exact,_quantized_matmul(x,weight,np.ones(3)))
    with pytest.raises(ValueError,match='accumulator'):
        CachedPredictor(MODEL,accumulator='int8')
    with pytest.raises(ValueError,match='2D INT8'):
        prepare_exact_weight(weight.astype(np.float32))
