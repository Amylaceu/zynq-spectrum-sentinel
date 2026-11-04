"""Z10 margin and report completeness must not silently become deployment PASS."""
from pathlib import Path
import shutil
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import summarize_z10_audit as audit


@pytest.fixture
def reports(tmp_path):
    source = audit.ROOT/'build/reports/sentinel_v2_100m/audit_reset_fix_r1'
    if not source.exists():
        pytest.skip('Requires retained local route reports')
    for name in audit.REPORTS:
        shutil.copyfile(source/name, tmp_path/name)
    return tmp_path


def test_small_positive_slack_does_not_pass_one_ns_target(reports):
    result = audit.summarize(reports)
    assert result['timing']['whs_ns'] == .028
    assert result['checks']['basic_timing_and_internal_coverage']
    assert result['checks']['z10_hold_margin']
    assert not result['checks']['z10_setup_margin']
    assert result['status'] == 'FAIL_AUTOMATED_GATES'


def test_primary_clock_redefinition_is_not_waived(reports):
    result = audit.summarize(reports)
    assert result['clock_root_issues'] == {'TIMING-4': 2, 'TIMING-27': 2}
    assert not result['checks']['no_redefined_primary_clocks']
    assert result['cdc_critical_counts']['CDC-1'] == 110


def test_missing_endpoint_evidence_fails_closed(reports):
    (reports/'endpoint_audit.txt').write_text('global_whs_ns 0.028\n')
    result = audit.summarize(reports)
    assert not result['checks']['unsafe_fifo_reset_d_count']
    assert not result['checks']['blackbox_count']


def test_missing_report_cannot_be_accepted(reports):
    (reports/'bus_skew.rpt').unlink()
    with pytest.raises(FileNotFoundError):
        audit.summarize(reports)


def test_drc_errors_are_not_silently_accepted(reports):
    path = reports/'drc.rpt'
    path.write_text(path.read_text()+'\n| TEST-1 | Error | Injected failure | 1 |\n')
    result = audit.summarize(reports)
    assert not result['checks']['drc_no_errors_or_critical']
    assert result['drc_rule_counts']['TEST-1']['count'] == 1


def test_truncated_drc_report_fails_closed(reports):
    (reports/'drc.rpt').write_text('Report DRC\n')
    result = audit.summarize(reports)
    assert not result['checks']['drc_summary_present']
    assert not result['checks']['drc_no_errors_or_critical']


def test_missing_route_error_count_fails_closed(reports):
    (reports/'route_status.rpt').write_text('Design Route Status\n')
    result = audit.summarize(reports)
    assert result['routing_errors'] is None
    assert not result['checks']['no_routing_errors']


def test_rule_details_do_not_duplicate_summary_counts():
    text = ('| TEST-1 | Critical Warning | Example | 3 |\n'
            'TEST-1#1 Critical Warning\nTEST-1#2 Critical Warning\n')
    assert audit.rule_counts(text) == {'TEST-1': {'severity': 'Critical Warning', 'count': 3}}
