import pytest
from tools.accept_sentinel_v1 import timing_summary,utilization

def timing(wns=.1,whs=.02):
    return f"checking no_clock (0)\nchecking unconstrained_internal_endpoints (0)\nWNS(ns) TNS(ns) Fail Total WHS(ns) THS(ns) Fail Total WPWS(ns) TPWS(ns) Fail Total\n-------\n{wns} 0 0 100 {whs} 0 0 100 .2 0 0 100\n"

def test_final_hold_is_a_gate_not_just_setup():
    assert timing_summary(timing())['WHS_ns']==.02
    with pytest.raises(ValueError,match='fails'):timing_summary(timing(whs=-.01))
    with pytest.raises(ValueError,match='coverage'):timing_summary(timing().replace('no_clock (0)','no_clock (3)'))

def test_resource_caps_are_enforced():
    text='| Slice LUTs | 39900 |\n| Slice Registers | 50000 |\n| Block RAM Tile | 110 |\n| DSPs | 40 |'
    assert utilization(text)['Block RAM Tile']==110
    with pytest.raises(ValueError,match='limits'):utilization(text.replace('110','110.5'))
    with pytest.raises(ValueError,match='limits'):utilization(text.replace('39900','39901'))
