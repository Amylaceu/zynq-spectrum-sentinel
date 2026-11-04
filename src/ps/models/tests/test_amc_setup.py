import numpy as np
import torch

from src.ps.models.amc_net import AMCNet
from src.ps.models.make_dataset import _group


def test_network_dimensions_gradients_and_cnn_baseline():
    torch.set_num_threads(2)
    torch.manual_seed(24)
    iq = torch.randint(-10000, 10001, (4, 2, 1024), dtype=torch.int16)
    hoc = torch.rand(4, 8)
    for with_hoc in (True, False):
        model = AMCNet(use_hoc=with_hoc)
        logits = model(iq, hoc)
        assert logits.shape == (4, 10) and torch.isfinite(logits).all()
        loss = torch.nn.functional.cross_entropy(logits, torch.arange(4))
        loss.backward()
        assert model.conv1.weight.grad.abs().sum() > 0
        if with_hoc:
            assert model.hoc_fc.weight.grad.abs().sum() > 0
        else:
            model.eval()
            torch.testing.assert_close(model(iq, hoc), model(iq, hoc + 100))


def test_preprocessing_removes_dc_and_normalizes_complex_power():
    torch.manual_seed(12)
    iq = torch.randn(3, 2, 1024) * 2000 + 3000
    y = AMCNet.normalize_iq(iq)
    torch.testing.assert_close(y.mean(dim=2), torch.zeros(3, 2), atol=1e-6, rtol=0)
    torch.testing.assert_close(y.square().sum(dim=1).mean(dim=1), torch.ones(3), atol=1e-6, rtol=0)
    assert torch.isfinite(AMCNet.normalize_iq(torch.zeros_like(iq))).all()


def test_dataset_seed_uniqueness_adc_alignment_and_fixed_hoc():
    a = _group((3, 7, 10))
    b = _group((3, 7, 10))
    for x, y in zip(a[2:6], b[2:6]):
        np.testing.assert_array_equal(x, y)
    iq, features, shifts, ids = a[2:6]
    assert iq.dtype == np.int16 and iq.shape == (10, 2, 1024)
    assert not np.any(iq & 15) and len(np.unique(ids)) == 10
    assert features.shape == (10, 8) and np.isfinite(features).all()
    centered = np.clip(np.rint(iq[0].T.astype(float) - iq[0].mean(axis=1)), -32768, 32767).astype(np.int16)
    words = centered.astype(np.int64) >> int(shifts[0])
    z = words[:, 0].astype(float) + 1j * words[:, 1]
    m20, m21, m40 = np.mean(z**2), np.mean(abs(z)**2), np.mean(z**4)
    expected = abs(m40 - 3 * m20**2) / m21**2
    assert abs(float(features[0, 1]) - expected) < 1e-5
    assert not set(ids) & set(_group((3, 8, 10))[5])


def test_differential_preprocessing_cancels_constant_phase():
    torch.manual_seed(234)
    x = torch.randn(4, 2, 1024)
    phase = 0.763
    rotated = torch.stack((x[:, 0] * np.cos(phase) - x[:, 1] * np.sin(phase),
                           x[:, 0] * np.sin(phase) + x[:, 1] * np.cos(phase)), dim=1)
    a = AMCNet.normalize_iq(x, "differential")
    b = AMCNet.normalize_iq(rotated, "differential")
    torch.testing.assert_close(a, b, atol=2e-6, rtol=1e-5)
    assert a.shape == x.shape and not torch.any(a[:, :, 0])
    model = AMCNet(input_mode="differential").eval()
    assert torch.isfinite(model(x, torch.ones(4, 8))).all()
