"""Backend injection preserves portable behavior; board tests cover native ABI."""
from pathlib import Path
import numpy as np
import pytest
from sim.golden.siggen import gen_mod
from src.ps.sentinel.amc.fine import gardner, refine
from src.ps.sentinel.amc.infer_np import Predictor
from src.ps.sentinel.amc.infer_native import NativeGardner

MODEL = Path(__file__).resolve().parents[1]/'models/weights/amc_v2/round_3/model.npz'

@pytest.mark.parametrize('family,label', [('PSK-high','QPSK'),('QAM','16QAM')])
def test_refiner_hook_same_output(family,label):
    iq = gen_mod(label,4096,8,fs=480000,seed=37)
    calls=[]
    def recovery(x,sps):
        calls.append((len(x),sps))
        return gardner(x,sps)
    left=refine(iq,family)
    right=refine(iq,family,timing_recovery=recovery)
    assert len(calls)==1 and calls[0][0]==4096
    for key in left:
        np.testing.assert_array_equal(left[key],right[key])

def test_predictor_refiner_injection_and_default():
    iq=gen_mod('QPSK',4096,8,fs=480000,seed=21)
    calls=[]
    def custom(x,family,fs):
        calls.append((family,fs))
        return refine(x,family,fs)
    left=Predictor(MODEL).predict(iq)[0]
    right=Predictor(MODEL,refiner=custom).predict(iq)[0]
    assert calls and left['label']==right['label']
    for key in ('confidence','coarse','class_index'):
        assert left[key]==right[key]
    np.testing.assert_array_equal(left['detail']['symbols'],right['detail']['symbols'])
    with pytest.raises(TypeError,match='callable'):
        Predictor(MODEL,refiner=42)

def test_missing_library_explicit_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        NativeGardner(tmp_path/'missing.so')
