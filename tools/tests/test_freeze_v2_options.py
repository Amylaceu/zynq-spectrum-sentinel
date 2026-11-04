"""An implementation-only option must be bound into the frozen receipt."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import freeze_v2_inputs as freeze


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    (tmp_path/'input.v').write_text('module input_stub; endmodule\n')
    monkeypatch.setattr(freeze, 'ROOT', tmp_path)
    monkeypatch.setattr(freeze, 'DIRECTORIES', ())
    monkeypatch.setattr(freeze, 'FILES', ('input.v',))
    return tmp_path


@pytest.mark.parametrize('mode', ['On', 'Off'])
def test_frozen_option_round_trip(inputs, monkeypatch, mode):
    args = ['freeze_v2_inputs.py', '--tag', 'test', '--power-optimization', mode]
    monkeypatch.setattr(sys, 'argv', args)
    freeze.main()
    receipt = inputs/'build/reports/sentinel_v2_100m/inputs_test.json'
    assert json.loads(receipt.read_text())['implementation_options']['power_optimization'] == mode
    monkeypatch.setattr(sys, 'argv', args+['--verify'])
    freeze.main()


def test_changed_option_fails_even_with_unchanged_sources(inputs, monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['freeze_v2_inputs.py', '--tag', 'test', '--power-optimization', 'Off'])
    freeze.main()
    monkeypatch.setattr(sys, 'argv', ['freeze_v2_inputs.py', '--tag', 'test', '--verify', '--power-optimization', 'On'])
    with pytest.raises(ValueError, match='option changed'):
        freeze.main()
