"""Summarize actual Z10 reports; never create a deployment PASS receipt.

A positive WHS is a hold pass under the analyzed constraints, not a substitute
for clock/IO/CDC review. The Z10 setup margin is separately checked at +1 ns.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from accept_sentinel_v1 import timing_summary, utilization
from accept_sentinel_v1b import bus_skew_summary
from accept_sentinel_y3 import check_audio_io
from timing_triage import parse_report

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ('timing.rpt', 'clocks.rpt', 'cdc.rpt', 'drc.rpt', 'methodology.rpt',
           'io.rpt', 'utilization.rpt', 'bus_skew.rpt', 'endpoint_audit.txt',
           'exceptions_summary.rpt', 'exceptions_ignored.rpt',
           'exceptions_coverage.rpt', 'critical_setup.rpt', 'critical_hold.rpt',
           'clock_interaction.rpt', 'route_status.rpt')


def rule_counts(text):
    """Read Vivado's summary table, not repeated rule details below it."""
    return {rule: dict(severity=severity, count=int(count))
            for rule, severity, count in re.findall(
                r'^\|\s*(\S+)\s*\|\s*(Critical Warning|Error|Warning)\s*\|'
                r'[^|\r\n]*\|\s*(\d+)\s*\|', text, re.M)}


def summarize(directory):
    texts = {name: (directory/name).read_text(errors='replace') for name in REPORTS}
    timing = parse_report(texts['timing.rpt'])
    errors = {}
    checks = {}
    for name, function, report in (
        ('basic_timing_and_internal_coverage', timing_summary, 'timing.rpt'),
        ('bus_skew', bus_skew_summary, 'bus_skew.rpt'),
        ('audio_pin_map', check_audio_io, 'io.rpt'),
    ):
        try:
            function(texts[report])
            checks[name] = True
        except ValueError as error:
            checks[name] = False
            errors[name] = str(error)
    summary = timing['summary']
    checks['z10_setup_margin'] = summary['wns_ns'] >= 1.0
    checks['z10_hold_margin'] = summary['whs_ns'] >= 0.0
    checks['routed_report'] = 'route' in (timing['design_state'] or '').lower()
    endpoint_counts = {}
    for key, expected in (('adc_status_first_stage_count', 2),
                          ('audio_first_stage_count', 1),
                          ('unsafe_fifo_reset_d_count', 0), ('blackbox_count', 0)):
        match = re.search(r'^'+key+r' (\d+)$', texts['endpoint_audit.txt'], re.M)
        endpoint_counts[key] = int(match[1]) if match else None
        checks[key] = endpoint_counts[key] == expected
    clock_root_issues = {key: len(re.findall(r'^'+key+r'#\d+',
                        texts['methodology.rpt'], re.M)) for key in ('TIMING-4', 'TIMING-27')}
    checks['no_redefined_primary_clocks'] = not any(clock_root_issues.values())
    cdc_counts = {key: int(count) for key, count in re.findall(
        r'^(CDC-\d+)\s+Critical\s+(\d+)\s', texts['cdc.rpt'], re.M)}
    drc = rule_counts(texts['drc.rpt'])
    # A missing/truncated report is not equivalent to zero DRC errors.
    checks['drc_summary_present'] = bool(re.search(
        r'Checks found:\s*\d+', texts['drc.rpt']))
    checks['drc_no_errors_or_critical'] = checks['drc_summary_present'] and not any(
        item['severity'] in ('Error', 'Critical Warning') and item['count']
        for item in drc.values())
    route_match = re.search(r'# of nets with routing errors\.+\s*:\s*(\d+)',
                            texts['route_status.rpt'])
    route_errors = int(route_match[1]) if route_match else None
    checks['no_routing_errors'] = route_errors == 0
    coverage = {key: int(count) for key, count in re.findall(
        r'checking (\w+) \((\d+)\)', texts['timing.rpt'])}
    methodology = rule_counts(texts['methodology.rpt'])
    # Deliberately no generic CDC waiver. These counts identify review work.
    pending = ['Review every CDC critical group and timing exception against RTL',
               'Review unconstrained external ports and actual IO clock assumptions',
               'Board single/three-tone/replay comparison, SAMPLE_DROP=0, LCD>=30fps',
               'Separate speaker tone and continuous-listening human acceptance']
    return dict(status='FAIL_AUTOMATED_GATES' if not all(checks.values()) else 'REVIEW_REQUIRED',
                scope='Report triage only; cannot authorize loading bitstream',
                recorded_utc=datetime.now(timezone.utc).isoformat(), checks=checks,
                errors=errors, timing=summary, resources=utilization(texts['utilization.rpt']),
                critical_setup_paths=timing['critical_max_paths'],
                endpoint_counts=endpoint_counts, clock_root_issues=clock_root_issues,
                cdc_critical_counts=cdc_counts, drc_rule_counts=drc,
                methodology_critical_counts={key: value['count'] for key, value in methodology.items()
                                             if value['severity'] == 'Critical Warning'},
                timing_coverage=coverage, routing_errors=route_errors, pending=pending)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    directory = (ROOT/args.audit_dir).resolve()
    output = (ROOT/args.output).resolve()
    sidecar = output.with_name(output.name+'.sha256')
    if not directory.is_relative_to(ROOT) or not output.is_relative_to(ROOT):
        parser.error('Paths must remain in this repository')
    if output.exists() or sidecar.exists():
        raise FileExistsError('Preserve previous report summary')
    result = summarize(directory)
    result['audit_dir'] = directory.relative_to(ROOT).as_posix()
    result['report_sha256'] = {name: hashlib.sha256((directory/name).read_bytes()).hexdigest()
                               for name in REPORTS}
    payload = (json.dumps(result, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    sidecar.write_text(hashlib.sha256(payload).hexdigest()+'  '+output.name+'\n', encoding='ascii')
    print(json.dumps(dict(status=result['status'], timing=result['timing'], checks=result['checks'])))


if __name__ == '__main__':
    main()
