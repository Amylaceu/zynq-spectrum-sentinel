"""Skew failures and missing audit output must block hardware deployment."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('accept_sentinel_v1b', Path(__file__).parents[1]/'accept_sentinel_v1b.py')
module = importlib.util.module_from_spec(spec)
with pytest.MonkeyPatch.context() as monkeypatch:
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    spec.loader.exec_module(module)


def test_multiple_constraints():
    text = 'Slack (MET) : 3.327ns\nSlack (MET) : 0.120ns'
    assert module.bus_skew_summary(text) == {'reported_paths':2, 'minimum_slack_ns':.120}


@pytest.mark.parametrize('text', ['', 'No constraints', 'Slack (VIOLATED) : -0.001ns',
                                  'Slack (MET) : -0.001ns', 'Slack (MET) : NaNns'])
def test_missing_or_failed_skew_blocks_acceptance(text):
    with pytest.raises(ValueError):
        module.bus_skew_summary(text)


def test_valid_path_does_not_hide_unparseable_path():
    with pytest.raises(ValueError):
        module.bus_skew_summary('Slack (MET) : 1.000ns\nSlack (MET) : NaNns')
