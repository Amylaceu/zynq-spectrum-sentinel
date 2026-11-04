import numpy as np

from sim.golden.pipeline import run
from sim.golden.siggen import to_int16_iq


def test_pipeline_tone_spectrum_and_no_fabricated_label():
    n = np.arange(2048 * 4)
    iq = to_int16_iq(0.3 * np.exp(2j * np.pi * 137 * n / 2048), backoff_db=0)
    result = run(iq, {"capture": False})
    assert result["spec_frames"].shape == (4, 2048)
    assert result["power_frames"].dtype == np.uint32
    assert np.argmax(result["power_frames"][-1]) == 1024 + 137
    targets = result["targets_per_frame"][-1]
    assert len(targets) == 1
    assert targets[0]["start"] <= 1024 + 137 <= targets[0]["stop"]
    assert result["labels"] == [] and result["captures"] == []
