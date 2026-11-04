"""Exercise the actual Tcl policy without loading or modifying an FPGA project."""
from pathlib import Path

import pytest

tkinter = pytest.importorskip('tkinter', reason='Tcl interpreter required for policy tests')


@pytest.fixture
def policy():
    interpreter = tkinter.Tcl()
    interpreter.eval('set calls {}; proc set_property {args} {lappend ::calls $args}')
    source = Path(__file__).resolve().parents[2]/'build/scripts/z10_impl_policy.tcl'
    interpreter.call('source', str(source))
    return interpreter


@pytest.mark.parametrize('mode,enabled', [('On', '1'), ('Off', '0')])
def test_both_power_steps_use_requested_mode(policy, mode, enabled):
    policy.call('sentinel_apply_power_policy', 'impl_1', mode)
    assert policy.eval('llength $calls') == '2'
    assert policy.eval('lindex $calls 0') == (
        'STEPS.POWER_OPT_DESIGN.IS_ENABLED '+enabled+' impl_1')
    assert policy.eval('lindex $calls 1') == (
        'STEPS.POST_PLACE_POWER_OPT_DESIGN.IS_ENABLED '+enabled+' impl_1')


def test_invalid_mode_rejected_before_any_project_mutation(policy):
    with pytest.raises(tkinter.TclError, match='On or Off'):
        policy.call('sentinel_apply_power_policy', 'impl_1', 'off')
    assert policy.eval('llength $calls') == '0'


def test_explicit_on_restores_both_steps_after_off(policy):
    policy.call('sentinel_apply_power_policy', 'impl_1', 'Off')
    policy.eval('set calls {}')
    policy.call('sentinel_apply_power_policy', 'impl_1', 'On')
    assert policy.eval('lindex $calls 0 1') == '1'
    assert policy.eval('lindex $calls 1 1') == '1'
