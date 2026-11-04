"""Whole-system metrics and real coarse-class scores, without hardware access."""
from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sentinel.telemetry import SystemMetrics
from sentinel.amc.infer_np import Predictor
from sentinel.amc.contract import COARSE_CLASSES


def test_proc_delta_memory_and_counter_reset(tmp_path):
    stat = tmp_path/'stat'
    stat.write_text('cpu 10 0 10 80 0 0 0 0 5 0\n')
    (tmp_path/'meminfo').write_text('MemTotal: 1000 kB\nMemAvailable: 400 kB\n')
    m = SystemMetrics(tmp_path)
    first = m.sample()
    assert first['ps_cpu_pct'] is None
    assert first['ps_memory_bytes'] == 600*1024
    stat.write_text('cpu 30 0 20 150 0 0 0 0 7 0\n')
    assert m.sample()['ps_cpu_pct'] == pytest.approx(30)
    stat.write_text('cpu 1 0 1 1 0 0 0 0\n')
    assert m.sample()['ps_cpu_pct'] is None
    stat.unlink()
    (tmp_path/'meminfo').write_text('MemTotal: 1000 kB\n')
    assert m.sample()['ps_memory_bytes'] is None


def test_top5_are_existing_softmax_scores_not_fabricated_fine_probabilities(monkeypatch):
    import sentinel.amc.infer_np as module
    monkeypatch.setattr(module, 'frontend', lambda iq: (None, None))
    predictor = Predictor.__new__(Predictor)
    logits = np.array([[0.,1.,2.,3.,4.,5.,6.,7.]])
    predictor.logits = lambda *args: logits
    prediction = predictor.predict(np.ones(4096, dtype=np.complex64))[0]
    assert prediction['label'] == 'FM'
    assert prediction['top5_scope'] == 'coarse8_softmax'
    probabilities = np.exp(logits[0]-7); probabilities /= probabilities.sum()
    assert len(prediction['top5']) == 5
    for i, value in zip(range(7,2,-1),prediction['top5']):
        assert value['label'] == COARSE_CLASSES[i]
        assert value['score'] == pytest.approx(probabilities[i])
    assert prediction['confidence'] == pytest.approx(probabilities[7])
