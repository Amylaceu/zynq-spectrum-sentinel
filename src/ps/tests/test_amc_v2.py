"""Contract, blind refinement, BN folding and integer accumulation regressions."""
import numpy as np
import pytest
import torch

from sim.golden.siggen import gen_mod
from src.ps.models.amc_l1 import AMCLevel1
from src.ps.models.export_int8_v2 import export
from src.ps.sentinel.amc.contract import SCHEMA
from src.ps.sentinel.amc.features import frontend
from src.ps.sentinel.amc.fine import refine
from src.ps.sentinel.amc.infer_np import Predictor, _quantized_matmul


@pytest.mark.parametrize('value', [np.zeros(4096, dtype=complex), np.ones(1024, dtype=complex),
                                 np.full(4096, np.nan+0j)])
def test_invalid_capture_rejected(value):
    with pytest.raises(ValueError):
        frontend(value)


def test_frontend_single_batch_and_gain_agree():
    x = gen_mod('FM', 4096, 8, fs=480000, seed=17)
    single = frontend(x)
    batch = frontend(np.stack((x, 11*x)))
    np.testing.assert_allclose(single[0][0], batch[0][1], atol=1e-6)
    np.testing.assert_allclose(single[1][0], batch[1][1], atol=2e-6)
    assert batch[0].shape == (2, 4, 512)


@pytest.mark.parametrize('label', ['QPSK', '8PSK'])
def test_blind_psk_with_unknown_phase_and_small_cfo(label):
    x = gen_mod(label, 4096, 8, fs=480000, cfo_hz=120, phase=.71, seed=23)
    result = refine(x, 'PSK-high')
    assert result['label'] == label
    assert len(result['symbols']) >= 300
    assert abs(result['sps']-8) < .1


def test_integer_mac_does_not_wrap_at_int8_boundary():
    x = np.full((1, 2, 4), 127, dtype=np.float32)
    qweight = np.full((3, 4), 127, dtype=np.int8)
    result = _quantized_matmul(x, qweight, np.ones(3))
    np.testing.assert_array_equal(result, np.full((1, 2, 3), 64516))


def test_folded_export_and_portable_inference_match_torch(tmp_path):
    torch.manual_seed(2)
    torch.set_num_threads(2)
    model = AMCLevel1().eval()
    # Nontrivial running statistics catch accidentally omitted BN folding.
    for index in range(1, 4):
        bn = getattr(model, 'bn'+str(index))
        bn.running_mean.copy_(torch.linspace(-.3, .4, len(bn.running_mean)))
        bn.running_var.copy_(torch.linspace(.5, 1.5, len(bn.running_var)))
    checkpoint = tmp_path/'model.pt'
    torch.save(dict(schema=SCHEMA, state_dict=model.state_dict(), smoke_only=True,
                    dataset_sha256='fixture'), checkpoint)
    exported = tmp_path/'model.npz'
    export(checkpoint, exported)
    samples = np.stack([gen_mod('FM', 4096, 8, fs=480000, seed=s) for s in (10, 11)])
    front, features = frontend(samples)
    with torch.inference_mode():
        expected = model(torch.from_numpy(front), torch.from_numpy(features)).numpy()
    runtime = Predictor(exported, 'fp32')
    np.testing.assert_allclose(runtime.logits(front, features), expected, atol=2e-5, rtol=2e-5)
    runtime.precision = 'int8'
    # Each capture's dynamic scale must be independent of batching.
    batched = runtime.logits(front, features)
    singles = np.concatenate([runtime.logits(front[i:i+1], features[i:i+1]) for i in range(2)])
    np.testing.assert_allclose(batched, singles, atol=1e-6)
    assert np.max(np.abs(batched-expected)) < .03
    with pytest.raises(ValueError):
        runtime.predict(samples, fs=3840000)
