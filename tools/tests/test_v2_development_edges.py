"""Regression for actual routed clock insertion, not the preceding BUFG node."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from accept_v2_development import edge_bounds


def report(kind, corner, insertion, delay):
    return f'''Slack: inf
Path Type: {kind} at {corner} Process Corner
Data Path Delay: {delay}ns
  BUFGCTRL_X0Y1 BUFG (Prop_bufg_I_O) 0.026 1.086 r clock/O
  net (fo=449, routed) 0.582 {insertion} i_system/audio/serializer/audio_mclk
  SLICE_X84Y62 FDRE r i_system/audio/serializer/lrck_reg/C
'''


def test_includes_clock_network_after_bufg():
    edges = edge_bounds(report('Max', 'Slow', 4.648, 8.929)
                        + report('Min', 'Fast', 1.668, 4.386))
    assert edges['early_ns'] == 6.054
    assert edges['late_ns'] == 13.577
    assert edges['paths'][0]['launch_clock_ns'] == 4.648


def test_missing_minimum_is_not_accepted():
    with pytest.raises(ValueError, match='Both physical'):
        edge_bounds(report('Max', 'Slow', 4.648, 8.929))


def test_missing_physical_insertion_is_not_accepted():
    with pytest.raises(ValueError, match='Missing launch'):
        edge_bounds(report('Max', 'Slow', 4.648, 8.929).replace('serializer/audio_mclk', 'other'))
